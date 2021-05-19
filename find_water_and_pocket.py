# -*- coding: utf-8 -*-
"""
Created on Thu May  6 09:47:21 2021

@author: yangl
"""

# -*- coding: utf-8 -*-
"""
Created on Mon Apr 12 09:03:24 2021
找到分子的pocket
1）建立格点，都标记为1
2）以分子的atom为圆心，r=vdw + 1.4做圆，圆内所有格点标记为0
4）以pas（protein accessible surface） 为圆心，r=10 or 20? ,圆内所有格点标记为0
@author: yangl
"""

# 打格点




import numpy as np
import pandas as pd
from common import vdw_radii
def gen_grid(coors, n=3, buffer=0):
    """ 
    coor: 分子的xyz
    n: 一埃内取点的个数
    """
    x_min = min(coors[:, 0])
    x_max = max(coors[:, 0])
    x_range = np.arange(int(x_min - buffer), int(x_max + buffer), n)
    y_min = min(coors[:, 1])
    y_max = max(coors[:, 1])
    y_range = np.arange(int(y_min - buffer), int(y_max + buffer), n)
    z_min = min(coors[:, 2])
    z_max = max(coors[:, 2])
    z_range = np.arange(int(z_min - buffer), int(z_max + buffer), n)
    xx, yy, zz = np.meshgrid(x_range, y_range, z_range)
    # 将其用ravel展开成一维，放入dataframe中，并都标记为 1
    res = pd.DataFrame({'x': xx.ravel(), 'y': yy.ravel(), 'z': zz.ravel()})
    return res.values


def sas_search_del(coors, elements, grids, pr=1.4):
    '''
    找到所有以 atom 为圆心，半径=vdw + pr 圆内所有的 格点
    并将其标记为 0
    coors: 分子的xyz坐标
    elements: 分子中元素
    grids: 为该分子生成的格点，np.array
    pr: 伸长的半径，一般为水分子的半径 1.4
    '''
    for index, coor in enumerate(coors):  # 循环格点
        r = vdw_radii[elements[index]] + pr
        d_ma = np.sum(np.square(coor - grids), axis=1)
        grids = grids[d_ma > np.square(r)]
    return grids


def pas_search_for_water(grids, pas, n=40, pr=20):
    '''
    pas:protein accessible surface
    找到所有以 pas 为圆心，半径=pr 圆内所有的 格点
    并将其标记为 0
    coors:分子的xyz坐标
    elements:分子的元素
    grids:经过sa_search_* 处理之后的格点
    '''

    for coor in pas[:, :-1]:  # 循环pas中的每个点
        d_ma = np.sum(np.square(coor - grids), axis=1)
        grids = grids[d_ma > np.square(pr-4.4)]
    return grids


def pas_search_for_pocket(grids, pas, n=40, pr=20):
    '''
    pas:protein accessible surface
    找到所有以 pas 为圆心，半径=pr 圆内所有的 格点
    并将其标记为 0
    grids:经过sa_search_* 处理之后的格点
    '''
    for coor in pas[:, :-1]:  # 循环pas中的每个点
        d_ma = np.sum(np.square(coor - grids), axis=1)
        grids = grids[d_ma > np.square(pr)]
    return grids


def pocket_search(water_grids, pocket_grids):
    for point in pocket_grids:
        d_ma = np.sum(np.square(point - water_grids), axis=1)
        water_grids = water_grids[d_ma > 1.0]
    return water_grids


def find_water(atoms_coors, elements, n=40, pas_r=20):
    from mol_surface import mol_surface_Vec
    pas = mol_surface_Vec.sa_surface_Vec(atoms_coors, elements, n=n, pr=pas_r)
    pocket_grids = gen_grid(atoms_coors, n=1)
    pocket_grids = sas_search_del(atoms_coors, elements, pocket_grids, pr=1.4)
    pocket_grids = pas_search_for_pocket(pocket_grids, pas, n=n, pr=pas_r)

    water_grids = gen_grid(atoms_coors, n=3, buffer=6)
    water_grids = sas_search_del(atoms_coors, elements, water_grids, pr=1.4)
    water_grids = pas_search_for_water(water_grids, pas, n=n, pr=pas_r)
    water_grids = pocket_search(water_grids, pocket_grids)
    return (water_grids, pocket_grids)

# if __name__ ==  '__main__':
#    test('6FS6-mono_noe4z.xyz')
