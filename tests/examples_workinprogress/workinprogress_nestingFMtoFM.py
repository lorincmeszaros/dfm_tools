# -*- coding: utf-8 -*-
"""
Created on Sat Nov 12 20:11:29 2022

@author: veenstra
"""

import os
import xarray as xr
from pathlib import Path
import pandas as pd
from scipy.spatial import KDTree
import numpy as np
import matplotlib.pyplot as plt
plt.close('all')
import contextily as ctx
try: #0.3.1 release
    #from hydrolib.core.io.net.models import NetworkModel, Network
    from hydrolib.core.io.polyfile.models import PolyFile
except: #main branch and next release
    #from hydrolib.core.io.dflowfm.net.models import NetworkModel, Network
    from hydrolib.core.io.dflowfm.polyfile.models import PolyFile

from dfm_tools.get_nc import get_netdata
from dfm_tools.hydrolib_helpers import pointlike_to_DataFrame
from dfm_tools.xarray_helpers import preprocess_hisnc
from dfm_tools.interpolate_grid2bnd import interp_hisnc_to_plipoints

#TODO: add coordinate conversion of pli coordinates
#TODO: add max distance for nestpoints (eg sqrt of max cell size of large grid? How to determine to use 3/4/more points)
#TODO: add conversion of sigma/z-sigma model (time-varying z coords) to T3D with fixed z reference?

dir_output = '.'


#NESTING PART 1
#get net and make KDTree of cellcenters
#file_net = r'p:\1230882-emodnet_hrsm\global_tide_surge_model\trunk\gtsm4.1\step11_global_1p25eu_net.nc' #TODO: cannot get netdata from this network, do in dfm_tools, hydrolib, xugrid, meshkernel?
file_net = r'p:\1230882-emodnet_hrsm\GTSMv5.0\runs\reference_GTSMv4.1_wiCA\output\gtsm_model_0000_map.nc'
crs_net = 'EPSG:4326'
data_net = get_netdata(file_net)
face_coords_pd = pd.DataFrame(dict(x=data_net.mesh2d_node_x,y=data_net.mesh2d_node_y))
tree_nest1 = KDTree(face_coords_pd)

#get and plot pli coordinates
file_pli_list = [Path(r'p:\i1000668-tcoms\03_newModel\01_input\02_bnd\pli\IndianOcean.pli'),
                 Path(r'p:\i1000668-tcoms\03_newModel\01_input\02_bnd\pli\PacificOcean.pli'),
                 Path(r'p:\i1000668-tcoms\03_newModel\01_input\02_bnd\pli\SeaOfJapan.pli'),
                 Path(r'p:\i1000668-tcoms\03_newModel\01_input\02_bnd\pli\TorresStrait.pli'),]

fig,ax = plt.subplots()
for file_pli in file_pli_list:
    polyfile_object = PolyFile(file_pli)
    data_pol_pd_list = [pointlike_to_DataFrame(polyobj) for polyobj in polyfile_object.objects]
    data_pol_pd = pd.concat(data_pol_pd_list)
    
    ax.plot(data_pol_pd['x'],data_pol_pd['y'],label=file_pli.name)
    
    #get and plot unique cell center coordinates
    plicoords_distance1, plicoords_cellidx = tree_nest1.query(data_pol_pd,k=4) #TODO: do on spherical globe (like gtsm obs snapping procedure)
    cellidx_uniq = np.unique(plicoords_cellidx)
    cellcoords = face_coords_pd.iloc[cellidx_uniq]
    cellcoords = cellcoords.reset_index() #revert from face numbers to 0-based, prevents SettingWithCopyWarning
    ax.plot(cellcoords['x'],cellcoords['y'],'x',label='{file_pli.name}_cellcenters')
    maxnumlen = cellcoords.index.astype(str).str.len().max()
    cellcoords['name'] = pd.Series(cellcoords.index).apply(lambda x: f'nestpoint_{x+1:0{maxnumlen}d}')
    
    #write nesting obspoints to file
    file_obs = os.path.join(dir_output,'{file_pli.name}_obs.xyn')
    cellcoords.to_csv(file_obs,sep='\t',index=False,header=False, float_format='%11.6f') #TODO: add hydrolib function once it exists
ax.legend()
ctx.add_basemap(ax=ax,attribution=False,crs=crs_net)
    
    
#NESTING PART 2
    
for file_pli in file_pli_list:
    kdtree_k = 4
    file_his = r'p:\1230882-emodnet_hrsm\GTSMv5.0\runs\reference_GTSMv4.1_wiCA\output\gtsm_model_0000_his.nc'
    data_xr_his = xr.open_mfdataset(file_his,preprocess=preprocess_hisnc)
    data_xr_his_selvars = data_xr_his[['waterlevel','velocity_magnitude']]
    
    data_interp = interp_hisnc_to_plipoints(data_xr_his=data_xr_his_selvars,file_pli=file_pli,kdtree_k=kdtree_k)
    



















