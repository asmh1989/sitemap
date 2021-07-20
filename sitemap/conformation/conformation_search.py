# -*- encoding: utf-8 -*-
"""
@Description:       :
利用ETKDG算法生成conformations,然后利用能量和RMS在尽量不损失精度的情况下，减小conformation的
数量。
@Date     :2021/06/23 10:58:30
@Author      :likun.yang
"""

import concurrent.futures
import copy
from multiprocessing import cpu_count

# sys.path.append("/home/yanglikun/git/")
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt

# from protein import mol_surface
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign
from rdkit.ML.Cluster import Butina

from sitemap.hydrophobicity.mol_surface import sa_surface

# import sys


platinum_diverse_dataset_path = "protein/conformation/dataset/platinum_diverse_dataset_2017_01.sdf"
bostrom_path = "protein/conformation/dataset/bostrom.sdf"
platinum_diverse_dataset = Chem.SDMolSupplier(platinum_diverse_dataset_path)
bostrom_dataset = Chem.SDMolSupplier(bostrom_path)


def process_mol(sdfMol):
    """
    do this, from sdf to smiles then to 3d, to remove the 3d 
    memory of the mol
    """
    molSmiles = Chem.MolToSmiles(sdfMol)
    mol = Chem.MolFromSmiles(molSmiles)
    return mol


# AllChem.MMFFOptimizeMolecule(mol_H, maxIters=200, mmffVariant="MMFF94s")
# Chem.AssignAtomChiralTagsFromStructure(mol_H, replaceExistingTags=True)

###################################################################################
def ChangeEpsilon(mol_H, id, maxIter, epilon):
    prop = AllChem.MMFFGetMoleculeProperties(mol_H, mmffVariant="MMFF94s")  # get MMFF prop
    prop.SetMMFFDielectricConstant(epilon)  # change dielectric constant, default value is 1
    ff = AllChem.MMFFGetMoleculeForceField(mol_H, prop, confId=id)  # load force filed
    ff.Initialize()
    ff.Minimize(maxIter)  # minimize the confs
    en = ff.CalcEnergy()
    return (id, en)


def ChangeEpsilonParallel(mol_H, epilon=1, maxIter=200):
    """并行化"""
    res = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=cpu_count()) as executor:
        futures = [executor.submit(ChangeEpsilon, mol_H, id, maxIter, epilon) for id in range(mol_H.GetNumConformers())]
        for future in concurrent.futures.as_completed(futures):
            # add result to total data
            res.append(future.result())
        # for id in range(mol_H.GetNumConformers()):
        #    future = executor.submit(task, mol_H, id, maxIter, epilon)
        # for future in concurrent.futures.as_completed(_futures):
        #    res.append(future.result())
    res.sort()  # in-place
    return np.array(res)[:, 1]


def change_epsilon(mol_H, epilon=1, maxIter=0):
    """可以并行化"""
    ens = []
    prop = AllChem.MMFFGetMoleculeProperties(mol_H, mmffVariant="MMFF94s")  # get MMFF prop
    prop.SetMMFFDielectricConstant(epilon)  # change dielectric constant, default value is 1

    for id in range(mol_H.GetNumConformers()):
        ff = AllChem.MMFFGetMoleculeForceField(mol_H, prop, confId=id)  # load force filed
        # ff.Minimize(maxIter)  # minimize the confs
        en = ff.CalcEnergy()
        ens.append(en)
    return np.array(ens)


def gen_conf(mol, RmsThresh=0.1, randomSeed=1, numThreads=0):
    nr = int(AllChem.CalcNumRotatableBonds(mol))
    Chem.AssignAtomChiralTagsFromStructure(mol, replaceExistingTags=True)
    if nr <= 3:
        nc = 50
    elif nr > 6:
        nc = 300
    else:
        nc = nr ** 3
    mol_H = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol_H, randomSeed=1)
    AllChem.EmbedMultipleConfs(
        mol_H, numConfs=nc, maxAttempts=1000, randomSeed=randomSeed, pruneRmsThresh=RmsThresh, numThreads=numThreads,
    )  # randomSeed 为了复现结果 #numThreads=0 means use all theads aviliable
    return mol_H


def calcConfRMSD(mol_H, ref_mol):
    RMSD = []
    mol_No_H = Chem.RemoveHs(mol_H)  # remove H to calc RMSD
    for indx, conformer in enumerate(mol_No_H.GetConformers()):
        conformer.SetId(indx)
        _rmsd = rdMolAlign.GetBestRMS(mol_No_H, ref_mol, prbId=indx)
        RMSD.append(_rmsd)
    return np.array(RMSD)


def calc_energy(mol_H, minimizeIts=200):
    results = {}
    num_conformers = mol_H.GetNumConformers()
    for conformerId in range(num_conformers):
        prop = AllChem.MMFFGetMoleculeProperties(mol_H, mmffVariant="MMFF94s")
        ff = AllChem.MMFFGetMoleculeForceField(mol_H, prop, confId=conformerId)
        ff.Initialize()
        if minimizeIts > 0:
            ff.Minimize(maxIts=minimizeIts)
        results[conformerId] = ff.CalcEnergy()
    return results


def calcConfEnergy(mol_H, maxIters=0):
    res = AllChem.MMFFOptimizeMoleculeConfs(mol_H, mmffVariant="MMFF94s", maxIters=maxIters, numThreads=0)
    return np.array(res)[:, 1]


def energyCleaning(mol_H, confEnergies, cutEnergy=5):
    res = confEnergies
    res = res - res.min()  # get relative energies
    # res = res - res.mean()
    removeIds = np.where(res > cutEnergy)[0]
    for id in removeIds:
        mol_H.RemoveConformer(int(id))
    for idx, conformer in enumerate(mol_H.GetConformers()):
        conformer.SetId(idx)
    return mol_H


def groupEnergyCleaing(mol_H, ConfEnergies, ButinaClusters):
    keepIdx = []
    molCopy = copy.deepcopy(mol_H)
    mol_H.RemoveAllConformers()
    for cluster in ButinaClusters:
        energyGroup = ConfEnergies[list(cluster)]
        df = pd.DataFrame([energyGroup, cluster]).T
        df = df.sort_values(0)
        idx = df[1].values[:1]
        keepIdx.extend(idx)
    for idx in keepIdx:
        mol_H.AddConformer(molCopy.GetConformer(int(idx)))
    return mol_H


def groupCleaing(mol_H, ButinaClusters):
    molCopy = copy.deepcopy(mol_H)
    mol_H.RemoveAllConformers()
    keepId = []
    for cluster in ButinaClusters:
        id = cluster[:2]
        keepId.extend(id)
    for id in keepId:
        mol_H.AddConformer(molCopy.GetConformer(int(id)))
    return mol_H


def getButinaClusters(mol_H, RmstThresh=0.5):
    molNoH = Chem.RemoveHs(mol_H)
    numConfs = molNoH.GetNumConformers()
    rmsma = AllChem.GetConformerRMSMatrix(molNoH)
    ButinaClusters = Butina.ClusterData(rmsma, numConfs, distThresh=RmstThresh, isDistData=True, reordering=True)
    return ButinaClusters


def postRmsClening(mol_H, RmstThresh=0.5):
    molCopy = copy.deepcopy(mol_H)
    ButinaClusters = getButinaClusters(mol_H, RmstThresh=RmstThresh)
    mol_H.RemoveAllConformers()
    for cluster in ButinaClusters:
        idx = cluster[0]
        mol_H.AddConformer(molCopy.GetConformer(idx))
    return mol_H


def localMinCleaning(mol_H, ConfEn):
    localMin = findLocalMin(ConfEn)
    idx = np.where(localMin)[0]
    molCopy = copy.deepcopy(mol_H)
    mol_H.RemoveAllConformers()
    for i in idx:
        mol_H.AddConformer(molCopy.GetConformer(int(i)))
    return mol_H


def findLocalMin(data):
    res = np.r_[True, data[1:] < data[:-1]] & np.r_[data[:-1] < data[1:], True]
    return res


def countCSPInSAS(molH, n=100):
    molNoH = Chem.RemoveHs(molH)
    res = []
    atoms = np.array([i.GetSymbol() for i in molNoH.GetAtoms()])
    numConfs = molNoH.GetNumConformers()
    for i in range(numConfs):
        conf = molNoH.GetConformer(i)
        pos = conf.GetPositions()
        sa = sa_surface(pos, atoms, n=n, enable_ext=False)
        carbonIdx = np.where((atoms == "C") | (atoms == "S") | (atoms == "P"))[0]
        tmp = np.isin(sa[:, -1], carbonIdx)
        numCarbon = np.count_nonzero(tmp)
        res.append(numCarbon / n)
    return np.array(res)


def NoUse(molH, n=100):
    molNoH = Chem.RemoveHs(molH)
    res = []
    atoms = np.array([i.GetSymbol() for i in molNoH.GetAtoms()])
    numConfs = molNoH.GetNumConformers()
    for i in range(numConfs):
        conf = molNoH.GetConformer(i)
        pos = conf.GetPositions()
        sa = sa_surface(pos, atoms, n=n, enable_ext=False)
        carbonIdx = np.where((atoms == "C") | (atoms == "S") | (atoms == "P"))[0]
        tmp = np.isin(sa[:, -1], carbonIdx)
        numCarbon = np.count_nonzero(tmp)
        res.append(numCarbon / n)
    return np.array(res)


def normalizeData(data):
    """
    project grad to [-1,1]
    grad = grad - grad.mean(axis=0) / grad.max(axis=0) - grad.min(axis=0)
    """
    a = data - data.mean(axis=0)
    b = data.max(axis=0) - data.min(axis=0)
    c = np.divide(a, b, out=np.zeros_like(a), where=b != 0)
    return c


def changeEnergyBaseOnSAS(en, normalizedNumC, coff=1):
    return en - coff * (en * normalizedNumC)


def changeEnergyBaseOnSASNoUse(en, sasa, coff=100):
    return en - coff * sasa


def run_Conf_Search(sdf_dataset, sample_size=100, cutEnergy=25, RmstThresh=1, coff=0.1, epilon=1):
    # num_mols = len(sdf_dataset)
    counter_1 = 0
    counter_2 = 0
    total_num_of_conformer = 0
    deltaSASA = []
    deltaE = []
    sample_size = sample_size
    np.random.seed(0)  # 为了结果的复现
    random_ll = np.random.randint(2859, size=(sample_size))
    for id in random_ll:
        sdf_mol = sdf_dataset[int(id)]
        mol = process_mol(sdf_mol)
        mol_H = gen_conf(mol, RmsThresh=0.5, randomSeed=1, numThreads=0)  # confs stored in side the mol object
        confEnergies = change_epsilon(mol_H, epilon=epilon)
        # confEnergies = calcConfEnergy(mol_H, maxIters=0)  #  get its energy
        # confEnergies = ChangeEpsilonParallel(mol_H, epilon=epilon)
        # lowestEnId = confEnergies.argmin()
        # normalizedNumC = countCSPInSAS(mol_H, n=100)
        # NumCSP = countCSPInSAS(mol_H, n=100)

        # confEnergies = changeEnergyBaseOnSAS(
        #    confEnergies, normalizedNumC, coff=coff
        # )
        # sasa = NoUse(mol_H)
        # confEnergies = changeEnergyBaseOnSASNoUse(confEnergies, sasa, coff=coff)
        mol_H = energyCleaning(mol_H, confEnergies, cutEnergy=cutEnergy)
        mol_H = postRmsClening(mol_H, RmstThresh=RmstThresh)
        # ButinaClusters = getButinaClusters(mol_H, RmstThresh=RmstThresh)
        # mol_H = groupEnergyCleaing(mol_H, confEnergies, ButinaClusters)
        # mol_H = groupCleaing(mol_H, ButinaClusters)
        # mol_H = localMinCleaning(mol_H, confEnergies)
        # mol_H = energyCleaning(mol_H, confEnergies, cutEnergy=cutEnergy)

        num_of_conformer = mol_H.GetNumConformers()
        total_num_of_conformer += num_of_conformer
        rmsd = calcConfRMSD(mol_H, sdf_mol)
        # lowestRMSId = rmsd.argmin()

        # deltaSASA.append(NumCSP[lowestRMSId] - NumCSP[lowestEnId])
        # deltaE.append(confEnergies[lowestRMSId] - confEnergies[lowestEnId])
        if np.any(rmsd <= 1):
            counter_1 += 1
        if np.any(rmsd <= 2):
            counter_2 += 1
    mean_conformer = total_num_of_conformer / sample_size
    reprocuce_rate_within_1 = counter_1 / sample_size
    reprocuce_rate_within_2 = counter_2 / sample_size
    print("{} mean num of conformers".format(int(mean_conformer)))
    print("{:.0%} reprocuce rate within RMSD 1".format(reprocuce_rate_within_1))
    print("{:.0%} reprocuce rate within RMSD 2".format(reprocuce_rate_within_2))
    # return (np.array(deltaSASA), np.array(deltaE), random_ll)


def plotEn(en, anno):
    plt.plot(en)
    plt.scatter(range(len(en)), en)
    for i, j in enumerate(anno):
        plt.annotate(round(j, 2), xy=(i, en[i]))


def alignConf(mol, ref):
    numConf = mol.GetNumConformers()
    for id in range(numConf):
        AllChem.AlignMol(mol, ref, prbCid=id, refCid=0)
    return 0


######################################################################
"""
begin to compare conformers and the target
"""
# mol_No_H = Chem.RemoveHs(mol_H)  # remove H to calc RMSD


# RMSD = []
# num_of_conformer = mol_No_H.GetNumConformers()
# print("Number of conformers:{}".format(num_of_conformer))

# for idx in range(num_of_conformer):
#     _rmsd = rdMolAlign.GetBestRMS(mol_No_H, sdfMol, prbId=idx)
#     RMSD.append(_rmsd)
# res = np.array(RMSD)


# per_under2 = np.count_nonzero(res <= 2.0) / num_of_conformer
# print("{:.0%} within RMSD 2".format(per_under2))

# per_under1 = np.count_nonzero(res <= 1.0) / num_of_conformer
# print("{:.0%} within RMSD 1".format(per_under1))
##########################################################

# ids = list(cids)  # You can reach conformers by ids


# results_UFF = AllChem.UFFOptimizeMoleculeConfs(mol_h_UFF, maxIters=max_iter)
# # results_MMFF = AllChem.MMFFOptimizeMoleculeConfs(mol_h_MMFF,maxIters=max_iter)


# # Search for the min energy conformer from results(tuple(is_converged,energy))
# print("Searching conformers by UFF ")
# for index, result in enumerate(results_UFF):
#     if min_energy_UFF > result[1]:
#         min_energy_UFF = result[1]
#         min_energy_index_UFF = index
#         print(min_energy_index_UFF, ":", min_energy_UFF)

# # print("\nSearching conformers by MMFF ")
# # for index, result in enumerate(results_MMFF):
# #    if(min_energy_MMFF>result[1]):
# #        min_energy_MMFF=result[1]
# #        min_energy_index_MMFF=index
# #        print(min_energy_index_MMFF,":",min_energy_MMFF)


# # Write minimum energy conformers into a SDF file
# w = Chem.SDWriter("minimum-energy-conformer-UFF.sdf")
# w.write(Chem.Mol(mol_h_UFF, False, min_energy_index_UFF))
# w.flush()
# w.close()