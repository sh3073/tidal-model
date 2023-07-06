import numpy as np
import datetime
import uptide
from thetis import *
import uptide.tidal_netcdf
import sys
import os.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
import params

# where should the output of this analysis go
output_dir = 'analysis'
create_directory(output_dir)

# where is the output of your model?
thetis_dir = params.output_dir

# was this run created with the DumbCheckpoint code? If so, make this True
legacy_run = False

# You *MAY* need to edit below this line
# Make sure below matches your main run file as much as possible
# *if* anything goes wrong with the analysis
#============================================================#

# making an assumption here on what the hdf5 output is called
chk = CheckpointFile("output/hdf5/Elevation2d_00000.h5",'r')
thetis_mesh = chk.load_mesh()

chk = CheckpointFile('bathymetry.h5','r')
bathymetry2d = chk.load_function(thetis_mesh,'bathymetry')
chk.close()
chk = CheckpointFile('manning.h5','r')
manning = chk.load_function(thetis_mesh, 'manning')
chk.close()

# How long does your simulations run for (s)
t_end = params.end_time #40 days (i.e. 30 days of analysis)
# how often are exports produced in the main run?
t_export = params.output_time
# which is the start file?
t_start = params.spin_up 

# Which tidal consituents to analyse?
constituent_order = ['M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4'] #LEAVE
constituents = params.constituents
# alter the ones used based on the Rayleigh Criterion
constituents = uptide.select_constituents(constituents, t_end - params.spin_up)

# You shouldn't need to edit below here
#========================================
t_n = int((t_end - t_start) / t_export) + 1
thetis_times = t_start + t_export*np.arange(t_n)


P1 = FunctionSpace(thetis_mesh, "CG", 1)
# we need bathy and manning on the same mesh as the elev and vel
P1DG = FunctionSpace(thetis_mesh, "DG", 1)
manningdg = project(manning, P1DG)
bathydg = project(bathymetry2d, P1DG)

elev = Function(P1DG, name='elev_2d')
elev_data_set = np.empty((t_n, elev.dat.data.shape[0]))
bathy = bathydg.dat.data[:]
man = manningdg.dat.data[:]
# we can now discard the functions
del(manningdg)
del(bathydg)

count = 0
for t in thetis_times:
    iexport = int(t/t_export)
    filename = '{0:s}_{1:05d}'.format("Elevation2d", iexport)
    print(filename)
    with CheckpointFile(os.path.join(thetis_dir,"hdf5",filename+".h5"), 'r') as afile:
        e = afile.load_function(thetis_mesh, "elev_2d")
        elev_data_set[count, :] = e.dat.data[:]
    count += 1

max_fs = [] # maximum tide height
min_fs = [] # minimum tide height

for i in range(elev.dat.data.shape[0]): # loop over nodes in the Function mesh
    all_elev = np.array(elev_data_set[:,i])
    max_fs.append(np.max(all_elev))
    min_fs.append(np.min(all_elev))



# we now sort out the tidal components
detector_amplitudes = []
detector_phases = []
detector_maxfs = []
detector_minfs = []
detector_tidal_range = []

for i in range(elev.dat.data.shape[0]):
    thetis_elev = elev_data_set[:,i]
    tide = uptide.Tides(constituents)
    tide.set_initial_time(params.start_datetime)

    # Subtract mean
    thetis_elev = thetis_elev - thetis_elev.mean()
    thetis_amplitudes, thetis_phases = uptide.analysis.harmonic_analysis(tide, thetis_elev[:], thetis_times[:])
    
    detector_maxfs.append(max(thetis_elev[:]))
    detector_minfs.append(min(thetis_elev[:]))
    detector_tidal_range.append(max(thetis_elev) - min(thetis_elev))
    detector_amplitudes.append(thetis_amplitudes)
    detector_phases.append(thetis_phases)

# sort out the min, max and tidal range - save as h5 to rasterise
with CheckpointFile(output_dir + '/tidal_stats_scal.h5', "w") as chk:
    chk.save_mesh(thetis_mesh)
    tr = Function(P1DG, name="TidalRange")
    tr.dat.data[:] = np.array(detector_tidal_range)
    chk.save_function(tr)
    File( output_dir + '/tidal_range.pvd').write(tr)

    for i in constituents:
        amp = Function(P1DG, name= i +'_amp')
        phase = Function(P1DG, name= i +'_phase')
        phasepi = Function(P1DG, name = i+'_phasepi')
        amp.dat.data[:] = np.array(detector_amplitudes)[:,constituents.index(i)]
        phase.dat.data[:] = np.array(detector_phases)[:,constituents.index(i)]
        chk.save_function(amp)
        chk.save_function(phase)
        File( output_dir + '/' + i + '_amp.pvd').write(amp)
        File( output_dir + '/' + i + '_phase.pvd').write(phase)
        phasepi.dat.data[:] = np.arcsin(np.sin(phase.dat.data[:]))
        File( output_dir + '/' + i + '_phase_mod_pi.pvd').write(phasepi)
        chk.save_function(phasepi)

# we're now done with the elevation data
del(elev_data_set)

uv = Function(P1DG, name='vel_2d')
u_data_set = np.empty((t_n, uv.dat.data.shape[0]))
v_data_set = np.empty((t_n, uv.dat.data.shape[0]))
bss_data_set = np.empty((t_n, elev.dat.data.shape[0]))
count = 0
for t in thetis_times:
    iexport = int(t/t_export)
    filename = '{0:s}_{1:05d}'.format("Elevation2d", iexport)
    print(filename)
    elev_data_set = []
    with CheckpointFile(os.path.join(thetis_dir,"hdf5",filename+".h5"), 'r') as afile:
        e = afile.load_function(thetis_mesh, "elev_2d")
        elev_data_set = e.dat.data[:]
    filename = '{0:s}_{1:05d}'.format("Velocity2d", iexport)
    with CheckpointFile(os.path.join(thetis_dir,"hdf5",filename+".h5"), 'r') as afile:
        uv = afile.load_function(thetis_mesh, "uv_2d")
        u_data_set[count, :] = uv.dat.data[:,0]
        v_data_set[count, :] = uv.dat.data[:,1]
    speed = np.sqrt(u_data_set[count, :]*u_data_set[count, :] + v_data_set[count, :]*v_data_set[count, :])
    elev_bathy = elev_data_set + bathy
    elev_bathy[elev_bathy < 0.01] = 0.0
    tau_b = np.array(1024*9.81*man*man*speed*speed / (elev_bathy)**(1./3.))
    tau_b[ elev_bathy < 0.001] = 0.0 # we have < 1mm of water
    tau_b[ tau_b < 0.0 ] = 0.0 # we had no water (shouldn't happen due to above, but just in case)
    bss_data_set[count, :] = tau_b
    count += 1


ave_speed = [] # average over speeds
max_speed = [] # max over speeds
ave_bss = [] # ave of bss calc
max_bss = [] # max of bss calc
ave_vel = [] # vector of ave u and ave v
max_vel = [] # vector of when max speed occurs

for i in range(uv.dat.data.shape[0]): # loop over nodes in the Function mesh
    man = np.array(manningdg.dat.data[i])
    bathy = np.array(bathydg.dat.data[i])
    u_vel = np.array(u_data_set[:,i]) # timeseries of u, v and elevation
    v_vel = np.array(v_data_set[:,i])
    speed = np.sqrt(u_vel*u_vel + v_vel*v_vel)
    ave_speed.append(np.mean(speed))
    max_speed.append(np.max(speed))
    tau_b = bss_data_set[:,i]
    ave_bss.append(np.mean(tau_b))
    max_bss.append(np.max(tau_b))

    ave_vel.append([np.mean(u_vel), np.mean(v_vel)])
    max_vel.append([u_vel[np.argmax(speed)],v_vel[np.argmax(speed)]])


# We then save all the scalar temporal stats in a single hdf5 file
with CheckpointFile(output_dir + '/temporal_stats_scal.h5', "w") as chk:
    chk.save_mesh(thetis_mesh)
    avespeed = Function(P1DG, name="AveSpeed")
    avespeed.dat.data[:] = np.array(ave_speed)
    File( output_dir + '/ave_speed.pvd').write(avespeed)
    chk.save_function(avespeed)
    maxspeed = Function(P1DG, name="MaxSpeed")
    maxspeed.dat.data[:] = np.array(max_speed)
    File( output_dir + '/max_speed.pvd').write(maxspeed)
    chk.save_function(maxspeed)
    avebss = Function(P1DG, name="AveBSS")
    avebss.dat.data[:] = np.array(ave_bss)
    File( output_dir + '/average_bss.pvd').write(avebss)
    chk.save_function(avebss)
    maxbss = Function(P1DG, name="MaxBSS")
    maxbss.dat.data[:] = np.array(max_bss)
    File( output_dir + '/max_bss.pvd').write(maxbss)
    chk.save_function(maxbss, name='MaxBSS')
    maxfs = Function(P1DG, name="MaxFS")
    maxfs.dat.data[:] = np.array(max_fs)
    chk.save_function(maxfs, name='MaxFS')
    File( output_dir + '/max_fs.pvd').write(maxfs)
    minfs = Function(P1DG, name="MinFS")
    minfs.dat.data[:] = np.array(min_fs)
    chk.save_function(maxfs, name='MinFS')
    File( output_dir + '/min_fs.pvd').write(minfs)

   
# now the vectors
with CheckpointFile(output_dir + '/temporal_stats_vec.h5', "w") as chk:
    chk.save_mesh(thetis_mesh)
    P1DG = VectorFunctionSpace(thetis_mesh, "DG", 1)
    avevel = Function(P1DG, name='ave_vel')
    avevel.dat.data[:] = np.array(ave_vel)
    File( output_dir + '/average_vel.pvd').write(avevel)
    chk.save_function(avevel, name='AveVel')
    maxvel = Function(P1DG, name='max_vel')
    maxvel.dat.data[:] = np.array(max_vel)
    File( output_dir + '/max_vel.pvd').write(maxvel)
    chk.save_function(maxvel, name='MaxVel')

