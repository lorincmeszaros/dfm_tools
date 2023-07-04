# -*- coding: utf-8 -*-
"""
Created on Thu Apr  6 18:46:35 2023

@author: veenstra
"""

import xugrid as xu
import meshkernel
import xarray as xr
import datetime as dt
import hydrolib.core.dflowfm as hcdfm
import pandas as pd
from dfm_tools.hydrolib_helpers import pointlike_to_DataFrame
from dfm_tools import __version__
import getpass
import numpy as np
from dfm_tools.coastlines import get_coastlines_gdb


def meshkernel_delete_withcoastlines(mk, res:str='f', min_area:float = 0, crs=None):
    """
    empty docstring
    """
    mesh_bnds = mk.mesh2d_get_mesh_boundaries_as_polygons()
    mesh_bnds.x_coordinates
    bbox = (mesh_bnds.x_coordinates.min(), mesh_bnds.y_coordinates.min(), mesh_bnds.x_coordinates.max(), mesh_bnds.y_coordinates.max())
    
    print('>> reading coastlines: ',end='')
    dtstart = dt.datetime.now()
    coastlines_gdb = get_coastlines_gdb(bbox=bbox, res=res, min_area=min_area, crs=crs)
    print(f'{(dt.datetime.now()-dtstart).total_seconds():.2f} sec')
    
    for coastline_geom in coastlines_gdb['geometry']: #TODO: also possible without loop? >> geometry_separator=-999.9 so that value can be used to concat polygons. >> use hydrolib poly as input? https://github.com/Deltares/MeshKernelPy/issues/35
        xx, yy = coastline_geom.exterior.coords.xy
        xx = np.array(xx)
        yy = np.array(yy)
        
        delete_pol_geom = meshkernel.GeometryList(x_coordinates=xx, y_coordinates=yy) #TODO: .copy()/to_numpy() makes the array contiguous in memory, which is necessary for meshkernel.mesh2d_delete()
        mk.mesh2d_delete(geometry_list=delete_pol_geom, 
                         delete_option=meshkernel.DeleteMeshOption(2), #ALL_COMPLETE_FACES/2: Delete all faces of which the complete face is inside the polygon
                         invert_deletion=False) #TODO: cuts away link that is neccesary, so results in non-orthogonal grid (probably usecase of english channel?)


def meshkernel_delete_withpol(mk, file_ldb, minpoints=None):
    """
    empty docstring
    """
    #TODO: read file_ldb as geodataframe (convert pointlike to geodataframe) and merge code with meshkernel_delete_withcoastlines
    
    print('>> reading+converting ldb: ',end='')
    dtstart = dt.datetime.now()
    pol_ldb = hcdfm.PolyFile(file_ldb)
    pol_ldb_list = [pointlike_to_DataFrame(x) for x in pol_ldb.objects] #TODO: this is quite slow, speed up possible?
    if minpoints is not None:
        pol_ldb_list = [x for x in pol_ldb_list if len(x)>minpoints] #filter only large polygons for performance
    for iP, pol_ldb in enumerate(pol_ldb_list):
        if not (pol_ldb.iloc[0] == pol_ldb.iloc[-1]).all(): #close the polygon if it is not yet closed
            pol_ldb_list[iP] = pd.concat([pol_ldb,pol_ldb.iloc[[0]]],axis=0)
    print(f'{(dt.datetime.now()-dtstart).total_seconds():.2f} sec')
    
    for iP, pol_del in enumerate(pol_ldb_list): #TODO: also possible without loop? >> geometry_separator=-999.9 so that value can be used to concat polygons. >> use hydrolib poly as input? https://github.com/Deltares/MeshKernelPy/issues/35
        delete_pol_geom = meshkernel.GeometryList(x_coordinates=pol_del['x'].to_numpy(), y_coordinates=pol_del['y'].to_numpy()) #TODO: .copy()/to_numpy() makes the array contiguous in memory, which is necessary for meshkernel.mesh2d_delete()
        mk.mesh2d_delete(geometry_list=delete_pol_geom, 
                         delete_option=meshkernel.DeleteMeshOption(2), #ALL_COMPLETE_FACES/2: Delete all faces of which the complete face is inside the polygon
                         invert_deletion=False) #TODO: cuts away link that is neccesary, so results in non-orthogonal grid (probably usecase of english channel?)


def meshkernel_to_UgridDataset(mk:meshkernel.meshkernel.MeshKernel, remove_noncontiguous:bool = False) -> xr.Dataset:
    """
    empty docstring
    """
    mesh2d_grid3 = mk.mesh2d_get()

    xu_grid = xu.Ugrid2d.from_meshkernel(mesh2d_grid3)
    
    #remove non-contiguous grid parts
    def xugrid_remove_noncontiguous(grid):
        #based on https://deltares.github.io/xugrid/examples/connectivity.html#connected-components
        #uses https://docs.scipy.org/doc/scipy/reference/sparse.csgraph.html
        #TODO: maybe replace with meshkernel?
        uda = xu.UgridDataArray(
            xr.DataArray(np.ones(grid.node_face_connectivity.shape[0]), dims=["face"]), grid
        )
        labels = uda.ugrid.connected_components()
        counts = labels.groupby(labels).count()
        most_frequent_label = counts["group"][np.argmax(counts.data)].item() #find largest contiguous part
        labels = labels.where(labels == most_frequent_label, drop=True)
        grid = labels.grid
        return grid
    if remove_noncontiguous:
        xu_grid = xugrid_remove_noncontiguous(xu_grid)
    
    #convert to dataset
    xu_grid_ds = xu_grid.to_dataset()
    
    #convert 0-based to 1-based grid for connectivity variables like face_node_connectivity #TODO: FM kernel needs 1-based grid, but it should read the attributes instead. Report this (#ug_get_meshgeom, #12, ierr=0. ** WARNING: Could not read mesh face x-coordinates)
    ds_idx = xu_grid_ds.filter_by_attrs(start_index=0)
    for varn_conn in ds_idx.data_vars:
        xu_grid_ds[varn_conn] += 1
        xu_grid_ds[varn_conn].attrs["_FillValue"] += 1
        xu_grid_ds[varn_conn].attrs["start_index"] += 1
    
    xu_grid_ds = xu_grid_ds.assign_attrs({#'Conventions': 'CF-1.8 UGRID-1.0 Deltares-0.10', #add Deltares convention (was CF-1.8 UGRID-1.0)
                                          'institution': 'Deltares',
                                          'references': 'https://www.deltares.nl',
                                          'source': f'Created with meshkernel {meshkernel.__version__}, xugrid {xu.__version__} and dfm_tools {__version__}',
                                          'history': 'Created on %s, %s'%(dt.datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z'),getpass.getuser()), #TODO: add timezone
                                          })
    
    # add attrs (to projected_coordinate_system/wgs84 empty int variable): #TODO: should depend on is_geographic flag in make_basegrid()
    # attribute_dict = {
    #     'name': 'WGS84',
    #     'epsg': np.array([4326], dtype=int),
    #     'grid_mapping_name': 'Unknown projected',
    #     'longitude_of_prime_meridian': np.array([0.0], dtype=float),
    #     'semi_major_axis': np.array([6378137.0], dtype=float),
    #     'semi_minor_axis': np.array([6356752.314245], dtype=float),
    #     'inverse_flattening': np.array([6356752.314245], dtype=float),
    #     'EPSG_code': 'EPSG:4326',
    #     'value': 'value is equal to EPSG code'}
    # xu_grid_ds['wgs84'] = xr.DataArray(np.array(0,dtype=int),dims=(),attrs=attribute_dict)
    
    xu_grid_uds = xu.UgridDataset(xu_grid_ds)
    return xu_grid_uds


def make_basegrid(lon_min,lon_max,lat_min,lat_max,dx,dy,angle=0,is_geographic=True):
    """
    empty docstring
    """
    print('modelbuilder.make_basegrid()')
    # create base grid
    make_grid_parameters = meshkernel.MakeGridParameters(angle=angle,
                                                         origin_x=lon_min,
                                                         origin_y=lat_min,
                                                         upper_right_x=lon_max,
                                                         upper_right_y=lat_max,
                                                         block_size_x=dx,
                                                         block_size_y=dy)
    
    mk = meshkernel.MeshKernel(is_geographic=is_geographic)
    mk.curvilinear_make_uniform_on_extension(make_grid_parameters)
    mk.curvilinear_convert_to_mesh2d() #convert to ugrid/mesh2d
    
    return mk


def refine_basegrid(mk, data_bathy_sel, min_edge_size):
    """
    empty docstring
    """
    print('modelbuilder.refine_basegrid()')
    
    lon_np = data_bathy_sel.lon.to_numpy()
    lat_np = data_bathy_sel.lat.to_numpy()
    values_np = data_bathy_sel.elevation.to_numpy().flatten().astype('float') #TODO: astype to avoid "TypeError: incompatible types, c_short_Array_74880 instance instead of LP_c_double instance"
    gridded_samples = meshkernel.GriddedSamples(x_coordinates=lon_np,y_coordinates=lat_np,values=values_np)


    #refinement
    mesh_refinement_parameters = meshkernel.MeshRefinementParameters(min_edge_size=min_edge_size, #always in meters
                                                                     refinement_type=meshkernel.RefinementType(1), #Wavecourant/1,
                                                                     connect_hanging_nodes=True, #set to False to do multiple refinement steps (e.g. for multiple regions)
                                                                     smoothing_iterations=2,
                                                                     max_courant_time=120)
    
    mk.mesh2d_refine_based_on_gridded_samples(gridded_samples=gridded_samples,
                                               mesh_refinement_params=mesh_refinement_parameters,
                                               use_nodal_refinement=True) #TODO: what does this do?
    
    return mk


def generate_bndpli(lon_min, lon_max, lat_min, lat_max, dlon, dlat, name='bnd'): #TODO: maybe generate with meshkernel?
    """
    empty docstring
    """

    vals_lon_ar = np.arange(lon_min, lon_max, dlon)
    vals_lon = np.linspace(lon_min, lon_max,len(vals_lon_ar))
    vals_lat_ar = np.arange(lat_min, lat_max, dlat)
    vals_lat = np.linspace(lat_min, lat_max,len(vals_lat_ar))
    pli_p1 = np.c_[np.repeat(lon_min,len(vals_lat)),vals_lat]
    pli_p2 = np.c_[vals_lon,np.repeat(lat_max,len(vals_lon))]
    pli_p3 = np.c_[np.repeat(lon_max,len(vals_lat)),vals_lat[::-1]]
    pli_p4 = np.c_[vals_lon[::-1],np.repeat(lat_min,len(vals_lon))]
    
    pli_all = np.concatenate([pli_p1[:-1],pli_p2[:-1],pli_p3[:-1],pli_p4[:-1]],axis=0)
    
    pli_polyobject = hcdfm.PolyObject(metadata=hcdfm.Metadata(name=name, n_rows=pli_all.shape[0], n_columns=pli_all.shape[1]),
                                      points=[hcdfm.Point(x=x,y=y,data=[]) for x,y in pli_all])
    pli_polyfile = hcdfm.PolyFile(objects=[pli_polyobject])
    return pli_polyfile


