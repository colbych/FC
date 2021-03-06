################################################################################
##
## Janus -- GUI Software for Processing Thermal-Ion Measurements from the
##          Wind Spacecraft's Faraday Cups
##
## Copyright (C) 2016 Bennett A. Maruca (bmaruca@udel.edu)
##
## This program is free software: you can redistribute it and/or modify it under
## the terms of the GNU General Public License as published by the Free Software
## Foundation, either version 3 of the License, or (at your option) any later
## version.
##
## This program is distributed in the hope that it will be useful, but WITHOUT
## ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
## FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
## details.
##
## You should have received a copy of the GNU General Public License along with
## this program.  If not, see http://www.gnu.org/licenses/.
##
################################################################################


###############################################################################
## LOAD THE NECESSARY MODULES.
################################################################################

# Load the modules necessary for signaling the graphical interface.

from PyQt4.QtCore import QObject, SIGNAL, QThread

# Load the modules necessary for file operations.

import os.path

# Load the modules necessary for handling dates and times.

from time import sleep
from datetime import datetime, timedelta
from janus_time import calc_time_epc, calc_time_sec, calc_time_val

# Load the module necessary handling step functions.

from janus_step import step

# Load the dictionary of physical constants.

from janus_const import const

# Load the modules necessary for loading Wind/FC and Wind/MFI data.

from janus_fc_arcv import fc_arcv
from janus_mfi_arcv import mfi_arcv

# Load the necessary array modules and mathematical functions.

from numpy import amax, amin, append, arccos, arctan2, arange, argsort, array, \
                    average, cos, deg2rad, diag, dot, exp, indices, interp, \
                    mean, pi, polyfit, rad2deg, reshape, sign, sin, sum, sqrt, \
                    std, tile, transpose, where, zeros

from numpy.linalg import lstsq

from scipy.interpolate import interp1d
from scipy.optimize import curve_fit
from scipy.special import erf
from scipy.stats import pearsonr, spearmanr

from janus_helper import round_sig

# Load the "pyon" module.

from janus_pyon import plas, series

# Load the modules necessary for saving results to a data file.

import pickle


################################################################################
## DEFINE THE "core" CLASS: THE ANLYSIS CORE OF JANUS.
################################################################################

class core( QObject ) :

	# +-------------------+------------------------------+
	# | SIGNAL('janus_*') | Arguments                    |
	# +-------------------+------------------------------+
	# | busy_beg          |                              |
	# | busy_end          |                              |
	# | mesg              | mesg_src, mesg_typ, mesg_obj |
	# | rset              |                              |
	# | chng_spc          |                              |
	# | chng_mfi          |                              |
	# | chng_mom_sel_cur  | t, p, v                      |
	# | chng_mom_sel_azm  | t, p                         |
	# | chng_mom_sel_all  |                              |
	# | chng_mom_res      |                              |
	# | chng_nln_pop      | i                            |
	# | chng_nln_ion      |                              |
	# | chng_nln_set      |                              |
	# | chng_nln_gss      |                              |
	# | chng_nln_sel_cur  | t, p, v                      |
	# | chng_nln_sel_all  |                              |
	# | chng_nln_res      |                              |
	# | chng_dsp          |                              |
	# | chng_dyn          |                              |
	# | done_auto_run     |                              |
	# | exit              |                              |
	# +-------------------+------------------------------+

	#-----------------------------------------------------------------------
	# DEFINE THE INITIALIZATION FUNCTION.
	#-----------------------------------------------------------------------

	def __init__( self, app=None, time=None ) :

		# Inheret all attributes of the "QObject" class.

		# Note.  This class does not directly provide any graphical
		#        interface.  Rather, the functions of the "QObject"
		#        class are used principally for signal the classes that
		#        do.

		super( core, self ).__init__( )

		self.app = app

		# Read and store the version information.

		# Note.  The "[:-1]" array operation used below trims the final
		#        character (which should be an end-line) from the line
		#        read from the file.

		fl = open( os.path.join( os.path.dirname( __file__ ),
		                         'janus.dat'                  ) )

		self.version = fl.readline( )[:-1]

		fl.close( )

		# Initialially deactiveate the debugging mode.

		self.debug = False

		# Initialize and store the archive of Wind/FC ion spectra.

		self.fc_arcv = fc_arcv( core=self )
		###self.fc_arcv = fc_arcv( core=self, use_idl=True,
		###                        buf=-1.                  )

		# Initialize and store the archive of Wind/MFI magnetic field
		# data.

		self.mfi_arcv = mfi_arcv( core=self )
		###self.mfi_arcv = mfi_arcv( core=self, use_k0=True,
		###                          buf=-1., tol=90.         )
		###self.mfi_arcv = mfi_arcv( core=self, use_idl=True,
		###                          buf=-1., tol=90.         )

		# Initialize a log of the analysis results.

		self.series = series( )

		# Initialize the variables that will contain the Wind/FC ion
		# spectrum's data, the associated Wind/MFI magnetic field data,
		# the ion spectrum's point selection, and the results of the
		# moments analysis of the ion spectrum.

		self.init_var( )

		# Load the requested Wind/FC ion spectrum (if one has been
		# requested).

		# Note.  After loading the Wind/FC ion spectrum,
		#        "self.load_spec" calls "self.load_mfi" to load the
		#        associated Wind/MFI magnetic field data and then calls
		#        "self.auto_sel" to make an automatic selection of the
		#        spectrum's data.  In turn, "self.auto_sel" calls
		#        "self.anls_mom" to perform a moments analysis on the
		#        selected data.

		if ( time is not None ) :

			self.load_spec( time )

	#-----------------------------------------------------------------------
	# INITIALIZE THE THE DATA AND ANALYSIS VARIABLES.
	#-----------------------------------------------------------------------

	def init_var( self ) :

		# Initialize the variables that will contain the Wind/FC ion
		# spectrum's data; the associated Wind/MFI magnetic field data;
		# and the settings, data selections, and results from all
		# analyses.

		self.rset_var( var_swe=True, var_mfi=True,
		               var_mom_win=True, var_mom_sel=True,
		               var_mom_res=True, var_nln_ion=True,
		               var_nln_set=True, var_nln_gss=True,
		               var_nln_sel=True, var_nln_res=True,
		               var_dsp=True, var_dyn=True          )

		# Define the data array with values for effective collecting
		# area, "eff_area", as a function of inflow angle, "deg".

		self.eff_deg  = arange( 0., 91., dtype=float )

		self.eff_area = 1.e-5 * array( [
		      3382000.0, 3383000.0, 3383000.0, 3382000.0, 3381000.0,
		      3380000.0, 3378000.0, 3377000.0, 3376000.0, 3374000.0,
		      3372000.0, 3369000.0, 3368000.0, 3364000.0, 3362000.0,
		      3359000.0, 3355000.0, 3351000.0, 3347000.0, 3343000.0,
		      3338700.0, 3334100.0, 3329300.0, 3324300.0, 3318200.0,
		      3312800.0, 3306300.0, 3299600.0, 3292800.0, 3285900.0,
		      3277800.0, 3270700.0, 3261600.0, 3253500.0, 3244500.0,
		      3234600.0, 3224900.0, 3200100.0, 3161500.0, 3114000.0,
		      3058820.0, 2997170.0, 2930000.0, 2857000.0, 2779000.0,
		      2694000.0, 2586999.7, 2465000.0, 2329999.6, 2183000.0,
		      2025999.6, 1859000.1, 1682999.6, 1497000.1, 1301999.6,
		      1099000.1, 887799.56, 668500.16, 452099.62, 257500.16,
		      96799.784, 539.96863, 0.0000000, 0.0000000, 0.0000000,
		      0.0000000, 0.0000000, 0.0000000, 0.0000000, 0.0000000,
		      0.0000000, 0.0000000, 0.0000000, 0.0000000, 0.0000000,
		      0.0000000, 0.0000000, 0.0000000, 0.0000000, 0.0000000,
		      0.0000000, 0.0000000, 0.0000000, 0.0000000, 0.0000000,
		      0.0000000, 0.0000000, 0.0000000, 0.0000000, 0.0000000,
		      0.0000000                                              ] )

		# Initialize the value of the indicator variable of whether the
		# automatic analysis should be aborted.

		# Note.  This variable provides the user with a means of
		#        prematurely stopping the automatic analysis of a series
		#        of spectra by the function "self.auto_run".  When that
		#        function is called, this indicator's value is set to
		#        "False".  After the function processes a given
		#        spectrum, it procedes on to the next one only if this
		#        indicator is still "False".

		self.stop_auto_run = False

	#-----------------------------------------------------------------------
	# RESET THE DATA AND ANALYSIS VARIABLES.
	#-----------------------------------------------------------------------

	def rset_var( self,
	              var_swe=False, var_mfi=False,
	              var_mom_win=False, var_mom_sel=False,
	              var_mom_res=False, var_nln_ion=False,
	              var_nln_set=False, var_nln_gss=False,
	              var_nln_sel=False, var_nln_res=False,
	              var_dsp=False, var_dyn=False          ) :

		# If requested, (re-)initialize the variables associated with
		# the ion spectrum's data.

		if ( var_swe ) :

			self.time_epc = None
			self.time_val = None
			self.time_txt = ''
			self.time_vld = True

			self.rot_sec = 3.
			self.dur_sec = 0.

			self.alt     = None
			self.azm     = None
			self.vel_cen = None
			self.vel_wid = None
			self.cur     = None
			self.cur_vld = None

			self.cur_jmp = 100.
			self.cur_min =   1.

			self.mag_t = None
			self.mag_x = None
			self.mag_y = None
			self.mag_z = None

			self.n_alt = 0
			self.n_azm = 0
			self.n_vel = 0

		# If requested, (re-)initialize the varaibles for the Wind/MFI
		# data associated with this spectrum.

		if ( var_mfi ) :

			self.n_mfi = 0

			self.mfi_dur = 0.

			self.mfi_t   = None
			self.mfi_b   = None
			self.mfi_b_x = None
			self.mfi_b_y = None
			self.mfi_b_z = None

			self.mfi_avg_mag = None
			self.mfi_avg_vec = None
			self.mfi_avg_nrm = None

			self.mfi_hat_dir = None

			self.psi_b       = None
                        self.psi_b_avg   = None

		# If requested, (re-)initialize the varaibles for the windows
		# associated with automatic data selection for the moments
		# analysis.

		if ( var_mom_win ) :

			self.mom_win_azm_req = 7
			self.mom_win_cur_req = 7

			self.mom_win_azm_txt = ''
			self.mom_win_cur_txt = ''

			self.mom_win_azm = self.mom_win_azm_req
			self.mom_win_cur = self.mom_win_azm_req

		# If requested, (re-)initialize the variables associated with
		# the data seleciton for the moments analysis.

		if ( var_mom_sel ) :

			self.mom_n_sel_azm = 0
			self.mom_n_sel_cur = None

			self.mom_min_sel_azm = 5
			self.mom_min_sel_cur = 3

			self.mom_sel_azm = None
			self.mom_sel_cur = None

		# If requested, (re-)initialize and store the variables
		# associated with the results of the moments analysis.

		if ( var_mom_res ) :

			self.mom_n_eta = 0

			self.mom_eta_ind_t = None
			self.mom_eta_ind_p = None

			self.mom_eta_n = None
			self.mom_eta_v = None
			self.mom_eta_w = None
			self.mom_eta_t = None

			self.mom_corr_pears = None
			self.mom_corr_spear = None

			self.mom_n = None
			self.mom_v = None
			self.mom_w = None
			self.mom_t = None
			self.mom_r = None

			self.mom_v_vec = None

			self.mom_w_per = None
			self.mom_w_par = None
			self.mom_t_per = None
			self.mom_t_par = None

			self.mom_cur = None

		# If requested, (re-)initialize the variables associated with
		# the ion species and populations for the non-linear analysis.

		# Note.  This includes both the "self.nln_spc_?" and
		#        "self.nln_pop_?" arrays.  These are done together since
		#        they are so interconnected by the "self.nln_pyon"
		#        object, which is also handled here.

		if ( var_nln_ion ) :

			self.nln_n_spc = 4
			self.nln_n_pop = 5

			self.nln_pyon = plas( enforce=True )

			self.nln_pop_use = tile( False, self.nln_n_pop )
			self.nln_pop_vld = tile( False, self.nln_n_pop )

			for s in range ( self.nln_n_spc ) :

				if ( s == 0 ) :
					self.nln_pyon.add_spec( name='Proton',
					                   sym='p', m=1., q=1. )
				elif ( s == 1 ) :
					self.nln_pyon.add_spec( name='Alpha' ,
					                   sym='a', m=4., q=2. )
				else :
					self.nln_pyon.add_spec( )

			for p in range ( self.nln_n_pop ) :

				if ( p == 0 ) :
					self.nln_pop_use[p] = True
					self.nln_pop_vld[p] = True
					self.nln_pyon.add_pop(
					        'p', name='Core', sym='c',
					        drift=False, aniso=True    )
				elif ( p == 1 ) :
					self.nln_pop_use[p] = False
					self.nln_pop_vld[p] = True
					self.nln_pyon.add_pop(
					        'p', name='Beam', sym='b',
					        drift=True , aniso=False   )
				elif ( p == 2 ) :
					self.nln_pop_use[p] = True
					self.nln_pop_vld[p] = True
					self.nln_pyon.add_pop(
					        'a', name='Core', sym='c',
					        drift=True , aniso=True    )
				elif ( p == 3 ) :
					self.nln_pop_use[p] = False
					self.nln_pop_vld[p] = True
					self.nln_pyon.add_pop(
					        'a', name='Beam', sym='b',
					        drift=True , aniso=False   )
				else :
					self.nln_pop_use[p] = False
					self.nln_pop_vld[p] = False
					self.nln_pyon.add_pop( None )

		# If requested, (re-)initialize the variables associated with
		# the settings for the automatic initial guess generation and
		# the automatic point selection.

		if ( var_nln_set ) :

			self.nln_set_gss_n   = tile( None , self.nln_n_pop )
			self.nln_set_gss_d   = tile( None , self.nln_n_pop )
			self.nln_set_gss_w   = tile( None , self.nln_n_pop )
			self.nln_set_gss_vld = tile( False, self.nln_n_pop )

			self.nln_set_sel_a   = tile( None , self.nln_n_pop )
			self.nln_set_sel_b   = tile( None , self.nln_n_pop )
			self.nln_set_sel_vld = tile( False, self.nln_n_pop )

			self.nln_set_gss_n[0] =  1.00
			self.nln_set_gss_n[1] =  0.20
			self.nln_set_gss_n[2] =  0.02
			self.nln_set_gss_n[3] =  0.01

			self.nln_set_gss_d[1] =  0.03
			self.nln_set_gss_d[2] =  0.01
			self.nln_set_gss_d[3] =  0.05

			self.nln_set_gss_w[0] =  1.00
			self.nln_set_gss_w[1] =  1.25
			self.nln_set_gss_w[2] =  1.00
			self.nln_set_gss_w[3] =  1.25

			self.nln_set_gss_vld[0] = True
			self.nln_set_gss_vld[1] = True
			self.nln_set_gss_vld[2] = True
			self.nln_set_gss_vld[3] = True

			self.nln_set_sel_a[0] = -3.00
			self.nln_set_sel_a[1] = -3.00
			self.nln_set_sel_a[2] = -3.00
			self.nln_set_sel_a[3] = -3.00
			self.nln_set_sel_a[4] = -3.00

			self.nln_set_sel_b[0] =  3.00
			self.nln_set_sel_b[1] =  3.00
			self.nln_set_sel_b[2] =  3.00
			self.nln_set_sel_b[3] =  3.00
			self.nln_set_sel_b[4] =  3.00

			self.nln_set_sel_vld[0] = True
			self.nln_set_sel_vld[1] = True
			self.nln_set_sel_vld[2] = True
			self.nln_set_sel_vld[3] = True
			self.nln_set_sel_vld[4] = True

		# If requested, (re-)initialize the variables associated with
		# the initial guesses for the non-linear analysis.

		if ( var_nln_gss ) :

			for p in range( self.nln_n_pop ) :
				self.nln_pyon.arr_pop[p]['n']     = None
				self.nln_pyon.arr_pop[p]['dv']    = None
				self.nln_pyon.arr_pop[p]['w']     = None
				self.nln_pyon.arr_pop[p]['w_per'] = None
				self.nln_pyon.arr_pop[p]['w_par'] = None

			self.nln_gss_vld = tile( False, self.nln_n_pop )

			self.nln_gss_pop = array( [ ] )
			self.nln_gss_prm = array( [ ] )

			self.nln_gss_cur_tot = None
			self.nln_gss_cur_ion = None

		# If requested, (re-)initialize the variables associated with
		# the data selection for the non-linear analysis.

		if ( var_nln_sel ) :

			self.nln_sel = None

			self.nln_n_sel   = 0
			self.nln_min_sel = 30

		# If requested, (re-)initialize the variables associated with
		# the results of the non-linear analysis.

		if ( var_nln_res ) :

			self.nln_res_plas = plas( enforce=False )

			self.nln_res_sel = None

			self.nln_res_cur_tot = None
			self.nln_res_cur_ion = None

		# If requested, (re-)initialize the variables which indicate of
		# the analyses have their results displayed in widgets which
		# support output from multiple analyses.

		if ( var_dsp ) :

			self.dsp = 'mom'

		# If requested, (re-)initialize the variables which indicate
		# which analyses are updated automatically when a change is
		# made to their settings.

		if ( var_dyn ) :

			self.dyn_mom = True
			self.dyn_gss = True
			self.dyn_sel = True
			self.dyn_nln = False

	#-----------------------------------------------------------------------
	# LOAD THE REQUESTED WIND/FC SPECTRUM.
	#-----------------------------------------------------------------------

	def load_spec( self, time_req=None,
	               get_prev=False, get_next=False,
	               tmin=None, tmax=None            ) :


		# Reset the variables that contain the Wind/FC ion spectrum's
		# data, the associated Wind/MFI magnetic field data, and the
		# results of all analyses.

		# Note.  Not all of the "self.rset_var" keywords are set to
		#        "True" so as to retain the general settings (even
		#        though a new spectrum is being loaded).

		self.emit( SIGNAL('janus_rset') )

		self.rset_var( var_swe=True, var_mfi=True,
		               var_mom_sel=True, var_mom_res=True,
		               var_nln_gss=True, var_nln_sel=True,
		               var_nln_res=True                    )


		# If a special code has been entered, take the specified action.

		if ( str( time_req ).lower( ) == 'iddqd' ) :

			self.emit( SIGNAL('janus_chng_spc') )

			if ( self.debug ) :
				self.debug = False
				self.emit( SIGNAL('janus_mesg'),
				           'core', 'end', 'debug' )
			else :
				self.debug = True
				self.emit( SIGNAL('janus_mesg'),
				           'core', 'begin', 'debug' )

			return


		# Convert the argument "time_req" into the standard, second-
		# precision, string format.  If this conversion returns "None",
		# label the requested time as invalid.

		self.time_txt = calc_time_sec( time_req )

		if ( self.time_txt is None ) :

			if ( type( time_req ) == str ) :
				self.time_txt = time_req
			else :
				self.time_txt = ''

			self.time_vld = False

		else :

			self.time_vld = True


		# If necessary, adjust "self.dsp" and "self.dyn_???" keywords to
		# make them a bit more mutually consistent.

		if ( ( self.dsp == 'gsl' ) or ( self.dsp == 'nln' ) ) :

			self.dyn_mom = True
			self.dyn_gss = True
			self.dyn_sel = True

			if ( ( self.dsp == 'nln' ) and ( not self.dyn_nln ) ) :

				self.dsp = 'gsl'

			self.emit( SIGNAL('janus_chng_dyn') )
			self.emit( SIGNAL('janus_chng_dsp') )


		# If no valid time was requested, alert the user and abort.

		if ( not self.time_vld ) :

			self.emit( SIGNAL('janus_mesg'),
			           'core', 'fail', 'time' )

			return


		# Message the user that a new Wind/FC ion spectrum is about to
		# be loaded.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'fc' )


		# Load the Wind/FC ion spectrum with a timestamp closest to that
		# requested.

		spec = self.fc_arcv.load_spec( self.time_txt,
		                               get_prev=get_prev,
		                               get_next=get_next,
		                               tmin=tmin, tmax=tmax )


		# If no spectrum was found, abort.

		if ( spec is None ) :

			self.emit( SIGNAL('janus_chng_spc') )

			return


		# Extract the parameters of the loaded Wind/FC ion spectrum.

		( time_epc,
		  cup1_azm  , cup2_azm  , cup1_c_vol, cup2_c_vol,
		  cup1_d_vol, cup2_d_vol, cup1_cur  , cup2_cur    ) = spec


		# Calculate and store the spectrum's properly formatted
		# timestamp both as a float and as a string.

		self.time_epc = time_epc
		self.time_val = calc_time_val( time_epc )
		self.time_txt = calc_time_sec( time_epc )
		self.time_vld = True


		# Convert bin centers and widths from voltages [V] to velocities
		# [km/s].

		cup1_vol_a = cup1_c_vol - ( cup1_d_vol / 2. )
		cup1_vol_b = cup1_c_vol + ( cup1_d_vol / 2. )

		cup2_vol_a = cup2_c_vol - ( cup2_d_vol / 2. )
		cup2_vol_b = cup2_c_vol + ( cup2_d_vol / 2. )

		cup1_c_vel = 1E-3 * sqrt( 2 * const['q_p'] * cup1_c_vol /
		                          const['m_p']                    )
		cup1_vel_a = 1E-3 * sqrt( 2 * const['q_p'] * cup1_vol_a /
		                          const['m_p']                    )
		cup1_vel_b = 1E-3 * sqrt( 2 * const['q_p'] * cup1_vol_b /
		                          const['m_p']                    )

		cup2_c_vel = 1E-3 * sqrt( 2 * const['q_p'] * cup2_c_vol /
		                          const['m_p']                    )
		cup2_vel_a = 1E-3 * sqrt( 2 * const['q_p'] * cup2_vol_a /
		                          const['m_p']                    )
		cup2_vel_b = 1E-3 * sqrt( 2 * const['q_p'] * cup2_vol_b /
		                          const['m_p']                    )

		cup1_d_vel = cup1_vel_b - cup1_vel_a
		cup2_d_vel = cup2_vel_b - cup2_vel_a


		# Determine the number of valid speed windows by searching
		# through the "c_vel_?" arrays and indentifying the first time
		# that an element is immediately followed by an element with a
		# smaller value.

		# Note.  The velocity windows should be assending order, and
		#        unused windows sould occur at the end of the "?_vel_?"
		#        and be indicated by having their corresponding elements
		#        in these arrays set to the instrument's minimum value
		#        for that parameter.

		n_vel = 1

		while ( ( n_vel < len( cup1_c_vel ) ) and
		        ( n_vel < len( cup2_c_vel ) )     ) :

			if ( ( cup1_c_vel[n_vel] < cup1_c_vel[n_vel-1] ) or
			     ( cup2_c_vel[n_vel] < cup2_c_vel[n_vel-1] )    ) :
				break
			else :
				n_vel += 1


		# Truncate the arrays to remove fill data.

		cup1_c_vel = cup1_c_vel[0:n_vel]
		cup1_d_vel = cup1_d_vel[0:n_vel]
		cup1_cur   = cup1_cur[:,0:n_vel]

		cup2_c_vel = cup2_c_vel[0:n_vel]
		cup2_d_vel = cup2_d_vel[0:n_vel]
		cup2_cur   = cup2_cur[:,0:n_vel]


		# Merge and store the arrays from the two cups.  As part of this
		# step, define the array of altitudes.

		# CAUTION!  There is currently no check to ensure that "c_vel_1"
		#           and "c_vel_2" are (to with floating point precision)
		#           identical.  Likewise, there is no check on "d_vel_1"
		#           and "d_vel_2".

		self.alt     = array( [ 15., -15. ] )           # deg
		self.azm     = array( [ cup1_azm, cup2_azm ] )  # deg
		self.vel_cen = cup1_c_vel                       # km/s
		self.vel_wid = cup1_d_vel                       # km/s
		self.cur     = array( [ cup1_cur, cup2_cur ] )  # pA


		# Store the counts of velocity bins and angles.

		self.n_alt =  2
		self.n_azm = 20
		self.n_vel = n_vel


		# Examine each measured current value and determine whether or
		# not it's valid for use in the proceding analyses.

		self.cur_vld = tile( True,
		                     [ self.n_alt, self.n_azm, self.n_vel ] )

		for t in range( self.n_alt ) :

			if ( n_vel < 2 ) :
				continue

			for p in range( self.n_azm ) :

				for v in range( self.n_vel ) :

					if ( self.cur[t,p,v] < self.cur_min ) :
						self.cur_vld[t,p,v] = False
						continue

					if ( v == 0 ) :
						if ( self.cur[t,p,v] >
						     ( self.cur_jmp *
						       self.cur[t,p,v+1] ) ) :
							self.cur_vld[t,p,v] = \
							                   False
							continue

					if ( v == ( self.n_vel - 1 ) ) :
						if ( self.cur[t,p,v] >
						     ( self.cur_jmp *
						       self.cur[t,p,v-1] ) ) :
							self.cur_vld[t,p,v] = \
							                   False
							continue

					if ( ( self.cur[t,p,v] >
					       ( self.cur_jmp *
					         self.cur[t,p,v-1] ) ) and
					     ( self.cur[t,p,v] >
					       ( self.cur_jmp *
					         self.cur[t,p,v+1] ) )     ) :
						self.cur_vld[t,p,v] = False


		# Estimate the duration of each spectrum and the mean time
		# offset of each velocity bin.

		self.rot_sec = 3.

		self.dur_sec = self.rot_sec * self.n_vel

		self.mag_t = self.rot_sec * ( arange( self.n_vel ) + 0.5 )


		# Message the user that a new Wind/FC ion spectrum has been
		# loaded.

		self.emit( SIGNAL('janus_mesg'), 'core', 'end', 'fc' )


		# Emit a signal that indicates that a new Wind/FC ion spectrum
		# has now been loaded.

		self.emit( SIGNAL('janus_chng_spc') )


		# Load the associated Wind/MFI magnetic field data associated
		# with this spectrum.

		self.load_mfi( )


		# If requested, run the moments analysis.

		if ( self.dyn_mom ) :
			self.anls_mom( )







		# FIXME
		"""
		# If requested (and required), generate an initial guess for
		# the non-linear analysis.

		if ( ( self.dyn_gss                 ) and
		     ( len( self.nln_gss_prm ) == 0 )     ) :
			self.auto_nln_gss( )


		# If requested (and required), select data for the non-linear
		# analysis.

		if ( ( self.dyn_sel         ) and
		     ( self.nln_sel is None )     ) :
			self.auto_nln_sel( )


		# If requested (and required), run the non-linear analysis.

		if ( ( self.dyn_nln            ) and
		     ( self.nln_res_n_ion == 0 )     ) :
			self.anls_nln( )
		"""







	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR LOADING THE Wind/MFI MAGNETIC FIELD DATA.
	#-----------------------------------------------------------------------

	def load_mfi( self ) :


		# Reset the contents of the "self.mfi_*" arrays.

		self.rset_var( var_mfi=True )


		# If no Wind/FC ion spectrum has been loaded, abort.

		if ( ( self.time_epc is None ) or
		     ( self.n_vel    is None ) or
		     ( self.n_vel    == 0    )    ) :
			return


		# Message the user that new Wind/MFI data are about to be
		# loaded.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'mfi' )


		# Load the Wind/MFI magnetic field data associated with this
		# spectrum.

		( mfi_t, mfi_b_x, mfi_b_y, mfi_b_z  ) = \
		          self.mfi_arcv.load_rang( self.time_val, self.dur_sec )


		# Establish the number of data.

		self.n_mfi = len( mfi_t )


		# If no magnetic field data were returned, abort with a signal
		# that the data have changed.

		if ( self.n_mfi == 0 ) :

			self.emit( SIGNAL('janus_chng_mfi') )

			return


		# Store the loaded data.  As part of this step, shift the data's
		# timestamps to be relative to the start time of this Wind/FC
		# ion spectrum.

		self.mfi_t = array( [ ( t - self.time_epc ).total_seconds( )
		                      for t in mfi_t                         ] )

		self.mfi_b_x   = mfi_b_x
		self.mfi_b_y   = mfi_b_y
		self.mfi_b_z   = mfi_b_z
                self.mfi_b_vec = [ self.mfi_b_x, self.mfi_b_y, self.mfi_b_z ]

		# Compute the magnetic field magnitude.

		self.mfi_b = sqrt( self.mfi_b_x**2 + self.mfi_b_y**2
		                                   + self.mfi_b_z**2 )


		# Compute the average magetic field.

		self.mfi_avg_vec = array( [ mean( self.mfi_b_x ),
		                            mean( self.mfi_b_y ),
		                            mean( self.mfi_b_z ) ] )

		self.mfi_avg_mag = sqrt( self.mfi_avg_vec[0]**2 +
		                         self.mfi_avg_vec[1]**2 +
		                         self.mfi_avg_vec[2]**2   )

		self.mfi_avg_nrm = self.mfi_avg_vec / self.mfi_avg_mag


		# Compute the dot product between the average, normalized
		# magnetic field and each look direction.

		self.mfi_hat_dir = array( [ [
		          dot( self.calc_dir_look( self.alt[t], self.azm[t,p] ),
		               self.mfi_avg_nrm )
		          for p in range( self.n_azm ) ]
		        for t in range( self.n_alt ) ] )

		# Compute the mfi angles.

		mfi_b_rho   = sqrt( mfi_b_x**2.0 + mfi_b_y**2.0 )
		mfi_b_colat = arctan2( mfi_b_z, mfi_b_rho       )
		mfi_b_lon   = arctan2( mfi_b_y, mfi_b_x         )
		mfi_b_colat = rad2deg( mfi_b_colat              )
		mfi_b_lon   = rad2deg( mfi_b_lon                )

		self.mfi_b_colat = mfi_b_colat
		self.mfi_b_lon   = mfi_b_lon

		self.mfi_avg_mag_angles = array( [mean( self.mfi_b_colat ),
		                                  mean( self.mfi_b_lon )] )


		# Use interpolation to estimate a magnetic-field vector for each
		# velocity bin.

		var_t = self.mag_t

		tk_lo = where( var_t < amin( self.mfi_t ) )
		tk_hi = where( var_t > amax( self.mfi_t ) )

		var_t[tk_lo] = amin( self.mfi_t )
		var_t[tk_hi] = amax( self.mfi_t )

		self.mag_x = interp1d( self.mfi_t, self.mfi_b_x,
		                       bounds_error=False        )( var_t )
		self.mag_y = interp1d( self.mfi_t, self.mfi_b_y,
		                       bounds_error=False        )( var_t )
		self.mag_z = interp1d( self.mfi_t, self.mfi_b_z,
		                       bounds_error=False        )( var_t )

		# Calculating the average angular deviation of magnetic field

                self.psi_b = sum( arccos( [ self.mfi_b_vec[i] * 
					    self.mfi_avg_nrm[i] /
                                            self.mfi_b[i] for i in range(3) ] ))

                self.psi_b_avg = self.psi_b/self.n_mfi

		# Message the user that new Wind/MFI data have been loaded.

		self.emit( SIGNAL('janus_mesg'), 'core', 'end', 'mfi' )


		# Emit a signal that indicates that a new Wind/MFI data have now
		# been loaded.

		self.emit( SIGNAL('janus_chng_mfi') )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR COMPUTING A DOT PRODUCT OR ARRAY THEREOF.
	#-----------------------------------------------------------------------

	def calc_arr_dot( self, a, b ) :


		# CAUTION!  It is assumed that "a" and "b" are "numpy" arrays.
		#           For increased speed, no checks are made of this.


		# If "a" and "b" are arrays of vectors, return an array where
		# each element is the dot product between the corresponding
		# element of "a" and that of "b".  If one of the arguments is
		# an array of vectors and the other is simply a vector, each an
		# array of the dot product between each element of the former
		# with the latter.  Otherwise, return the dot product between
		# "a" and "b".

		if ( hasattr( a[0], '__iter__' ) and
		     hasattr( b[0], '__iter__' )     ) :

			return array( [ dot( a[i], b[i] )
			                for i in range(
			                         min( [ len(a), len(b) ] ) ) ] )

		elif ( hasattr( a[0], '__iter__' ) ) :

			return array( [ dot( v, b ) for v in a ] )

		elif ( hasattr( b[0], '__iter__' ) ) :

			return array( [ dot( a, v ) for v in b ] )

		else :

			return dot( a, b )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR COMPUTING A UNIT VECTOR OR ARRAY THEREOF.
	#-----------------------------------------------------------------------

	def calc_arr_nrm( self, a ) :


		# CAUTION!  It is assumed that "a" is a "numpy" array.  For
		#           increased speed, no check are made of this.


		# If "a" is an array of vectors, return an array where each
		# element is the normalized version of the corresponding
		# elements of "a".  Otherwise, return the normalized version of
		# "a".

		if ( hasattr( a[0], '__iter__' ) ) :

			return array( [ v / sqrt( sum( v**2 ) ) for v in a ] )

		else :

			return a / sqrt( sum( a**2 ) )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CLIPPING A VALUE OR ARRAY OF VALUES.
	#-----------------------------------------------------------------------

	def calc_arr_clp( self, a, lwr, upr ) :


		# If "a" is an array of vectors, return a clipped version of
		# "a" where each element falls between "lwr" and "upr".
		# Otherwise, clip "a" as a scalar.

		if hasattr( a, '__iter__' ) :

			return array( [ min( [ max( [ v, lwr ] ), upr ] )
			                for v in a                        ] )

		else :

			return min( [ max( [ a, lwr ] ), upr ] )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CONVERT ALT-AZM TO A CARTESIAN UNIT VECTOR.
	#-----------------------------------------------------------------------

	def calc_dir_look( self, alt, azm ) :


		# Convert altitude and azimuth the spherical coordinates.

		the = - alt + 90.
		phi = - azm


		# Convert from spherical to rectangular coordinates and return
		# the result.

		ret = array( [
		        sin( deg2rad( the ) ) * cos( deg2rad( phi ) ),
		        sin( deg2rad( the ) ) * sin( deg2rad( phi ) ),
		        cos( deg2rad( the ) )                          ] )

		if ( ret.ndim > 1 ) :
			return transpose( ret )
		else :
			return ret


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CALCULATING THE EFFECTIVE AREA OF THE CUP.
	#-----------------------------------------------------------------------

	def calc_eff_area( self, d, v ) :


		# Note.  The argument "d" is a vector (in a Cartesian coordinate
		#        system) that indicates the look direction of the cup.
		#        The argument "v" is a similar vector that indicates the
		#        particle velocity.  The magnitudes of "d" and "v" are
		#        irrelevant as the angle between "d" and "-v" is the
		#        only parameter used in this function.  The returned
		#        value of the effective collecting area is in units of
		#        square centimeters.


		# Normalize the look direction and particle velocity.

		dn = self.calc_arr_nrm( d )
		vn = self.calc_arr_nrm( v )


		# Calculate the particle inflow angle (in degrees) relative to
		# the cup normal (i.e., the cup pointing direction).

		psi = rad2deg( arccos( self.calc_arr_dot( dn, -vn ) ) )
		psi = self.calc_arr_clp( psi, 0., 90. )


		# Return the effective collecting area corresponding to "psi".

		if hasattr( psi, '__iter__' ) :

			return array( [
			            interp( p, self.eff_deg, self.eff_area )
			            for p in psi                             ] )

		else :

			return interp( psi, self.eff_deg, self.eff_area )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CALCULATING EXPECTED CURRENT (MAXWELLIAN).
	#-----------------------------------------------------------------------

	def calc_cur_max( self,
	                  vel_cen, vel_wid,
	                  dir_alt, dir_azm,
	                  prm_n, prm_v_x, prm_v_y, prm_v_z, prm_w ) :


		# Return the equivalent bi-Maxwellian response for equal
		# perpendicular and parallel thermal speeds and a dummy
		# magnetic field.

		return self.calc_cur_bmx( vel_cen, vel_wid,
		                          dir_alt, dir_azm, 1., 0., 0.,
		                          prm_n, prm_v_x, prm_v_y, prm_v_z,
		                          prm_w, prm_w                      )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CALCULATING EXPECTED CURRENT (BI-MAXWELLIAN).
	#-----------------------------------------------------------------------

	def calc_cur_bmx( self,
	                  vel_cen, vel_wid,
	                  dir_alt, dir_azm,
	                  mag_x, mag_y, mag_z,
	                  prm_n, prm_v_x, prm_v_y, prm_v_z,
	                  prm_w_per, prm_w_par              ) :


		# Note.  This function is based on Equation 2.34 from Maruca
		#        (PhD thesis, 2012), but differs by a factor of $2$
		#        (i.e., the factor of $2$ from Equation 2.13, which is
		#        automatically calibrated out of the Wind/FC data).


		# Calcualte the vector bulk velocity.

		prm_v = array( [ prm_v_x, prm_v_y, prm_v_z ] )

		if ( prm_v.ndim > 1 ) :
			prm_v = transpose( prm_v )


		# Calculate the look direction as a cartesian unit vector.

		dlk = self.calc_dir_look( dir_alt, dir_azm )


		# Calculate the direction of the magnetic field as a cartesian
		# unit vector.

		mag = array( [ mag_x, mag_y, mag_z ] )

		if ( mag.ndim > 1 ) :
			mag = transpose( mag )

		dmg = self.calc_arr_nrm( mag )


		# Calculate the component of the magnetic field unit vector
		# along that lies along the look direction.

		dmg_dlk = self.calc_arr_dot( dmg, dlk )


		# Compute the effective thermal speed along this look direction.


		prm_w = sqrt( ( ( 1. - dmg_dlk**2 ) * prm_w_per**2 ) +
		              (        dmg_dlk**2   * prm_w_par**2 )   )


		# Calcuate the exponential terms of the current.

		ret_exp_1 = 1.e3 * prm_w * sqrt( 2. / pi ) * exp(
		            - ( ( vel_cen - ( vel_wid / 2. )
		            - self.calc_arr_dot( dlk, -prm_v ) )
		            / prm_w )**2 / 2. )
		ret_exp_2 = 1.e3 * prm_w * sqrt( 2. / pi ) * exp(
		            - ( ( vel_cen + ( vel_wid / 2. )
		            - self.calc_arr_dot( dlk, -prm_v ) )
		            / prm_w )**2 / 2. )


		# Calculate the "erf" terms.

		ret_erf_1 = 1.e3 * self.calc_arr_dot( dlk, -prm_v ) * erf(
		            ( vel_cen - ( vel_wid / 2. )
		            - self.calc_arr_dot( dlk, -prm_v ) )
		            / ( sqrt(2.) * prm_w ) )
		ret_erf_2 = 1.e3 * self.calc_arr_dot( dlk, -prm_v ) * erf(
		            ( vel_cen + ( vel_wid / 2. )
		            - self.calc_arr_dot( dlk, -prm_v ) )
		            / ( sqrt(2.) * prm_w ) )


		# Calculate the parenthetical expression.

		ret_prn = ( ( ret_exp_2 + ret_erf_2 ) -
		            ( ret_exp_1 + ret_erf_1 )   )


		# Calculate the expected current.

		ret = ( ( 1.e12 ) * ( 1. / 2. ) * ( const['q_p'] )
		        * ( 1.e6 * prm_n )
		        * ( 1.e-4 * self.calc_eff_area( dlk, prm_v ) )
		        * ( ret_prn ) )


		# Return the calculated value for the expected current.

		return ret


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR AUTOMATIC DATA SELECTION FOR THE MOMENTS ANAL.
	#-----------------------------------------------------------------------

	def auto_mom_sel( self,
	                  win_azm=None, win_cur=None, no_anls_mom=False ) :


		# Note.  The each of the "win_???" keywords is expected to be
		#        either an integer or a string-expression of an integer.


		# Re-initialize the data-selection variables for the moments
		# analysis.

		self.rset_var( var_nln_sel=True )


		# If it exists, store the value of each of the "win_???"
		# keywords as a string.

		# Note.  This step is used to provide a record of keyword
		#        input that cannot be converted to an integer.  In
		#        such cases, the corresponding variable
		#        "self.req_win_???" is given a value of "None".  This
		#        invalid input is principally saved so that it can be
		#        displayed in the user-input text-box.

		if ( win_azm is not None ) :
			self.mom_win_azm_txt = str( win_azm )

		if ( win_cur is not None ) :
			self.mom_win_cur_txt = str( win_cur )


		# Attempt to extract any user-provided widths.

		# Note.  No change is made to the value of a given
		#        "self.mom_win_???_req" variable if the value of the
		#        corresponding "win_???" keyword is "None" (either
		#        because the user passed no value or passed a value of
		#        "None").  If the user passes an invalid value, though,
		#        "self.mom_win_???_req" is set to "None" and no change
		#        is made to the corresponding "self.mom_win_???" value.

		if ( win_azm is not None ) :
			try :
				self.mom_win_azm_req = int( win_azm )
			except :
				self.mom_win_azm_req = None

		if ( win_cur is not None ) :
			try :
				self.mom_win_cur_req = int( win_cur )
			except :
				self.mom_win_cur_req = None


		# Begin by setting the window sizes to those requested by the
		# user (if available).

		if ( self.mom_win_azm_req is not None ) :
			self.mom_win_azm = self.mom_win_azm_req

		if ( self.mom_win_cur_req is not None ) :
			self.mom_win_cur = self.mom_win_cur_req


		# Now, validate (and, if necessary, adjust) the sizes of the
		# automatic selection windows.

		self.mom_win_azm = max( self.mom_win_azm, self.mom_min_sel_azm )
		self.mom_win_azm = min( self.mom_win_azm, self.n_azm           )

		self.mom_win_cur = max( self.mom_win_cur, self.mom_min_sel_cur )
		self.mom_win_cur = min( self.mom_win_cur, self.n_vel           )


		# First, select the look directions with the strongest signal,
		# which are indicated in the "self.mom_sel_azm" array.

		self.auto_mom_sel_azm( )


		# Second, for each selected look direction, select the data with
		# the strongest signal and indicate this selection in the
		# "self.mom_sel_cur" array.

		self.auto_mom_sel_cur( )


		# Instruct each of the registered widgets to update based on the
		# potential change in selection status of each datum.

		# Emit a signal that indicates that the selection status of all
		# data for the moments analysis has changed.

		self.emit( SIGNAL('janus_chng_mom_sel_all') )


		# Validate the new data selection (i.e., make sure that the two
		# "self.mom_sel_???" arrays are self consistent).

		self.vldt_mom_sel( )


		# Unless requested otherwise, run the moments analysis (and
		# then, if the non-linear analysis is set to be dynamically
		# updated, run that analysis as well).

		if ( not no_anls_mom ) :

			self.anls_mom( )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR AUTO-SELECTING LOOK DIRECTIONS FOR MOMENTS.
	#-----------------------------------------------------------------------

	def auto_mom_sel_azm( self ) :


		# CAUTION!  It is strongly recommended that this function only
		#           be called by "self.auto_mom_sel( )", which first
		#           calls "self.auto_mom_sel_azm( )" and then calls
		#           "self.auto_mom_sel_cur( )".  Neither of the calls
		#           to the "self.auto_mom_sel_???( )" functions
		#           validates the data or updates the
		#           "self.n_mom_sel_???" counters; this is instead
		#           handled by "self.auto_mom_sel( )" with a call to
		#           "self.vldt_mom_sel( )".


		# Initially, deselect all look directions.

		self.mom_sel_azm = tile( False, [ self.n_alt, self.n_azm ] )

		self.mom_n_sel_azm = 0


		# Initialize the "max_cur" and "mm_cur" arrays.

		# Note.  The former will be populated with the maximum current
		#        seen in each velocity window.  The latter (the min-max
		#        array) will be populated with the minimum value over a
		#        running, circular "p"-window of "self.mom_win_azm"
		#        elements from the "max_cur" array.

		max_cur = zeros( [ self.n_alt, self.n_azm ] )
		mm_cur  = zeros( [ self.n_alt, self.n_azm ] )


		# Populate the "max_cur" array.

		for t in range( self.n_alt ) :

			for p in range( self.n_azm ) :

				tk = where( self.cur_vld[t,p,:] )[0]

				if ( len( tk ) > 0 ) :
					max_cur[t,p] = max( self.cur[t,p,tk] )
				else :
					max_cur[t,p] = 0.


		# Populate the "mm_cur" array.

		for t in range( self.n_alt ) :

			for p in range( self.n_azm ) :

				for w in range( self.mom_win_azm ) :

					mm_cur[t,p] += \
					             max_cur[t,(p+w)%self.n_azm]


		# Find the location of the maximum value of each row of the
		# "mm_cur" array and use this location to update the
		# corresponding row of "self.mom_sel_azm".

		for t in range( self.n_alt ) :

			p0 = where( mm_cur[t,:] ==
			                 amax( mm_cur[t,:] ) )[0][0]

			for p in range( p0, p0+self.mom_win_azm ) :

				self.mom_sel_azm[t,p%self.n_azm] = True


		# Record the number of selected look directions.

		self.mom_n_sel_azm = len( where( self.mom_sel_azm )[0] )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNC. FOR AUTO-SELECTING INDIVIDUAL DATA FOR MOMENTS ALAL.
	#-----------------------------------------------------------------------

	def auto_mom_sel_cur( self ) :


		# CAUTION!  It is strongly recommended that this function only
		#           be called by "self.auto_mom_sel( )", which first
		#           calls "self.auto_mom_sel_azm( )" and then calls
		#           "self.auto_mom_sel_cur( )".  Neither of the calls
		#           to the "self.auto_mom_sel_???( )" functions
		#           validates the data or updates the
		#           "self.n_mom_sel_???" counters; this is instead
		#           handled by "self.auto_mom_sel( )" with a call to
		#           "self.vldt_mom_sel( )".


		# CAUTION!  This function only selects data from look directions
		#           that have already been selected (i.e., those for
		#           which their corresponding elements of
		#           "self.mom_sel_azm" is "True".  It is assumed that
		#           the function "self.auto_sel_azm( )" is called
		#           immediately prior a call of this function.


		# Initially, de-select all data.

		self.mom_sel_cur = tile( False, [ self.n_alt, self.n_azm,
		                                  self.n_vel              ] )

		self.mom_n_sel_cur = tile( 0, [ self.n_alt, self.n_azm ] )


		# Loop through all look directions.  For each that has been
		# selected, select a portion of the data therefrom.

		v_rng = arange( self.n_vel )

		for t in range( self.n_alt ) :

			for p in range( self.n_azm ) :

				# If the current look direction was not
				# selected, move on to the next one as clearly
				# no data should be selected from this one.

				if ( not self.mom_sel_azm[t,p] ) :
					continue

				# Consider all spans of "self.mom_win_cur"
				# indices and select the data from the one with
				# the highest total current.

				v_0   = 0
				cur_0 = 0.

				for v in range( self.n_vel - self.mom_win_cur) :

					tk = where( ( v_rng >= v           ) &
					            ( v_rng < ( v +
					                self.mom_win_cur ) ) &
					            ( self.cur_vld[t,p,:]  )   )

					if ( len( tk ) > 0 ) :
						cur_v = sum( self.cur[t,p,tk] )
					else :
						cur_v = 0.

					if ( cur_v > cur_0 ) :
						v_0   = v
						cur_0 = cur_v

				self.mom_sel_cur[
				          t,p,v_0:(v_0+self.mom_win_cur)] = True


		# Record the number of data selected in each look direction.

		self.mom_n_sel_cur = array( [ [
		                len( where( self.mom_sel_cur[t,p,:] )[0] )
		                              for p in range( self.n_azm ) ]
		                                for t in range( self.n_alt ) ] )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING THE SELECTION OF A SINGLE POINT.
	#-----------------------------------------------------------------------

	def chng_mom_sel( self, t, p, v ) :


		# Change the selection of the requested datum.

		self.mom_sel_cur[t,p,v] = not self.mom_sel_cur[t,p,v]


		# Emit a signal that indicates that the datum's selection status
		# for the moments analysis has changed.

		self.emit( SIGNAL('janus_chng_mom_sel_cur'), t, p, v )


		# Validate the new data selection (i.e., make sure that the two
		# "self.sel_???" arrays are mutually-consistent) and update the
		# "self.n_sel_???" counters.

		self.vldt_mom_sel( )


		# Ensure that the moments analysis has been set for "dyanmic"
		# mode (since the user presumably wants it this way).  Rerun the
		# moments analysis.

		# Note.  An alternative behavior would be to check the value of
		#        "self.dyn_mom" (without changing it) and then rerunning
		#        the moments analysis only if this parameter has the
		#        value "True".

		self.chng_dyn( 'mom', True, rerun=False )

		self.anls_mom( )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR VALIDATING THE DATA SELECTION.
	#-----------------------------------------------------------------------

	def vldt_mom_sel( self ) :


		# Note.  This function ensures that the two "self.mom_sel_???"
		#        arrays are mutually consistent.  For each set of "t"-
		#        and "p"-values, "self.mom_sel_azm[t,p]" can only be
		#        "True" if at least "self.min_sel_cur" of the elements
		#        in "self.mom_sel_cur[t,p,:]" are "True".  However, if
		#        fewer than "self.mom_min_sel_azm" sets of "t"- and
		#        "p"-values satisfy this criterion, all elements of
		#        "self.mom_sel_azm" are given the value "False".
		#
		#        Additionally, this functions serves to update the
		#        "self.mom_n_sel_???" counters.


		# Save the initial selection of pointing directions.

		old_mom_sel_azm = self.mom_sel_azm


		# Update the counter "self.mom_n_sel_cur" (i.e., the number of
		# selected data in each pointing direction).

		self.mom_n_sel_cur = array( [ [
		                len( where( self.mom_sel_cur[t,p,:] )[0] )
		                              for p in range( self.n_azm ) ]
		                                for t in range( self.n_alt ) ] )

		# Create a new selection of pointing directions based on the
		# data selection, and then update the counter
		# "self.mom_n_sel_azm".

		self.mom_sel_azm = array( [ [
		           self.mom_n_sel_cur[t,p] >= self.mom_min_sel_cur
		                              for p in range( self.n_azm ) ]
		                                for t in range( self.n_alt ) ] )

		self.mom_n_sel_azm = len( where( self.mom_sel_azm )[0] )


		# Determine the total number of selected pointing directions; if
		# this number is less than the minimum "self.mom_min_sel_azm",
		# deselect all pointing directions.

		mom_n_sel_azm = len( where( self.mom_sel_azm )[0] )

		if ( mom_n_sel_azm < self.mom_min_sel_azm ) :

			self.mom_sel_azm = tile( False,
			                         [ self.n_alt, self.n_azm ] )

			self.mom_n_sel_azm = 0


		# Identify differences between the new and old versions of
		# "self.mom_sel_azm".  For each pointing direction whose
		# selection status for the moments analysis has changed, emit a
		# signal indicating this.

		( tk_t, tk_p ) = where( self.mom_sel_azm != old_mom_sel_azm )

		n_tk = len( tk_t )

		for k in range( n_tk ) :

			self.emit( SIGNAL('janus_chng_mom_sel_azm'),
			           tk_t[k], tk_p[k]                  )


	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR RUNNING THE MOMENTS ANALYSIS.
	#-----------------------------------------------------------------------

	def anls_mom( self ) :


		# Re-initialize and the output of the moments analysis.

		self.rset_var( var_mom_res=True )


		# If the point-selection arrays have not been populated, run
		# the automatic point selection.

		if ( ( self.mom_sel_azm is None ) or
		     ( self.mom_sel_cur is None )    ) :

			self.auto_mom_sel( no_anls_mom=True )


		# If any of the following conditions are met, emit a signal that
		# indicates that the results of the moments analysis have
		# changed, and then abort.
		#   -- No (valid) ion spectrum has been requested.
		#   -- No ion spectrum has been loaded.
		#   -- The primary ion species is not available for analysis.
		#   -- No initial guess has been generated.
		#   -- Insufficient data have been selected.

		if ( ( self.time_epc is None                     ) or
		     ( self.n_vel == 0                           ) or
		     ( self.mom_n_sel_azm < self.mom_min_sel_azm )    ) :

			self.emit( SIGNAL('janus_mesg'),
			           'core', 'norun', 'mom' )

			self.emit( SIGNAL('janus_chng_mom_res') )

			return


		# Message the user that the moments analysis has begun.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'mom' )


		# Extract the "t"- and "p"-indices of each selected pointing
		# direction.

		( tk_t, tk_p ) = where( self.mom_sel_azm )


		# Initialize the "eta_*" arrays.

		# Note.  Only some of these arrays will ultimate be saved.

		# Note.  The arrays "eta_?" define the density, inflow speed,
		#        thermal speed, and temperature derived for each of the
		#        analyzed look directions.

		n_eta = self.mom_n_sel_azm

		eta_phi = tile( 0., n_eta )
		eta_the = tile( 0., n_eta )

		eta_dlk = tile( 0., [ n_eta, 3 ] )  # Cartesian look direction

		eta_eca = tile( 0., n_eta )         # effective collecting area

		eta_n   = tile( 0., n_eta )         # number density
		eta_v   = tile( 0., n_eta )         # inflow speed
		eta_w   = tile( 0., n_eta )         # thermal speed
		eta_t   = tile( 0., n_eta )         # temperature


		# For each of the selected look directions, identify the
		# selected data therefrom and calculate the estimator of the
		# projected inflow speed along that direction.

		# Note.  Equations 3.11, 3.13, and 3.15 of my dissertation
		#        (Maruca, PhD thesis, 2012) contain an extra factor of
		#        $2$ that is omitted below in the calculation of the
		#        estimators.  This factor reflects the half-efficiency
		#        that is inherent to the use of demodulation and has
		#        already been taken into account in the calibration of
		#        the current measurments.

		for k in range( n_eta ) :

			# Extract the "t"- and "p"-values for this direction.

			t = tk_t[k]
			p = tk_p[k]

			# Store the $\theta$- and $\phi$-values for this look
			# direction.

			eta_the[k] = - self.alt[t] + 90.
			eta_phi[k] = - self.azm[t,p]

			# Convert the look direction from altitude-azimuth to a
			# Cartesian unit vector.

			eta_dlk[k,:] = self.calc_dir_look( self.alt[t],
			                                   self.azm[t,p] )

			# Extract the "v" values of the selected data from this
			# look direction.

			v = where( self.mom_sel_cur[t,p,:] )[0]

			eta_v[k] = - sum( self.cur[t,p,v] ) / \
			                sum( self.cur[t,p,v] / self.vel_cen[v] )


		# Use singular value decomposition (in the form of least squares
		# analysis) to calculate the best-fit bulk speed for the solar
		# wind.

		mom_v_vec = lstsq( eta_dlk, eta_v )[0]

		mom_v = sqrt( mom_v_vec[0]**2 + mom_v_vec[1]**2
		                              + mom_v_vec[2]**2 )


		# For each of the selected look directions, use the derived
		# value of "mom_v_vec" to estimate its effective collecting
		# area, the number density, and the thermal speed.

		for k in range( n_eta ) :

			# Extract the "t"- and "p"-values for this direction.

			t = tk_t[k]
			p = tk_p[k]

			# Calculate the effective collecting area for this look
			# direction.

			eta_eca[k] = self.calc_eff_area( eta_dlk[k,:],
			                                 mom_v_vec     )

			# Extract the "v" indices of the selected data from this
			# look direction.

			v = where( self.mom_sel_cur[t,p,:] )[0]

			# Estimate the number density and thermal speed based on
			# the selected data from this look direction.

			eta_n[k] = 1e-6 * ( ( 1. / const['q_p'] )
			           / ( 1.e-4 * eta_eca[k] )
			           * sum( ( 1.e-12 * self.cur[t,p,v] ) /
			                  ( 1.e3 * self.vel_cen[v]   )   ) )

			eta_w[k] = 1e-3 * sqrt( max( [ 0.,
			           ( ( 1. / const['q_p'] )
			           / ( 1.e-4 * eta_eca[k] )
			           / ( 1.e6 * eta_n[k] )
			           * sum( ( 1.e-12 * self.cur[t,p,v] ) *
			                  ( 1.e3 * self.vel_cen[v]   )   ) )
			           - ( 1e3 * eta_v[k] )**2               ] ) )


		# Compute the effective temperature for each of the analyzed
		# look directions.

		eta_t = ( 1.E-3 / const['k_b'] ) * \
		        const['m_p'] * ( ( 1.E3 * eta_w )**2 )


		# Calculate a net estimator of the number density.

		# Note.  The total signal for a look direction is roughly
		#        proportional to its effective collecting area.  Thus,
		#        the reciprical of the effective collecting area can be
		#        thought of a crude indicator of the uncertainty in the
		#        number-density estimators from the corresponding look
		#        direction.

		mom_n = average( eta_n, weights=eta_eca**2 )


		# Initialize the temporary variable the indicates whether or not
		# the temperature anisotropy analysis has been successfully
		# performed.  If there are some magnetic field data, at least
		# attempt the analysis.  Otherewise, skip it.

		if ( self.n_mfi > 0 ) :
			aniso = True
		else :
			aniso = False


		# If indicated, attempt to compute the components of thermal
		# speed and temperature.  If this fails (or could not be
		# attempted because of a lack of magnetic field data), simply
		# compute the scalar values.

		if ( aniso ) :

			# Construct the "data" arrays that will be used to
			# determine the components of the thermal speed.

			# Note.  Assuming a bi-Maxwellian distribution, the
			#        square of a look direction's thermal speed
			#        should be a linear function of the square of
			#        the dot product between the look direction and
			#        the direction of the magnetic field.  See
			#        Equation 2.32 by Maruca (PhD thesis, 2012).

			dat_x = array( [ self.mfi_hat_dir[tk_t[k],tk_p[k]]
			                 for k in range( n_eta )          ] )**2

			dat_y = eta_w**2

			# If the "x" data array has insufficient coverage for a
			# reliable linear fit, abort the anisotropy analysis.

			if ( amax( dat_x ) == amin( dat_x ) ) :
				aniso = False

		if ( aniso ) :

			# Perform the linear fit.

			( f_slope, f_icept ) = polyfit( dat_x, dat_y, 1 )

			# If the returned fit parameters are non-physical, abort
			# the anisotropy analysis.

			if ( (   f_icept             <= 0 ) or
			     ( ( f_icept + f_slope ) <= 0 )    ) :
				aniso = False

		if ( aniso ) :

			# Use the values returned for the fit parameters to
			# calculate the components of thermal speed and
			# temperature.

			mom_w_per = sqrt( f_icept )
			mom_w_par = sqrt( f_icept + f_slope )

			mom_t_per = ( 1.E-3 / const['k_b'] ) * \
			            const['m_p'] * ( 1.E6 * f_icept )
			mom_t_par = ( 1.E-3 / const['k_b'] ) * \
			            const['m_p'] * \
			            ( 1.E6 * ( f_icept + f_slope ) )

			# Compute the scalar thermal speed and temperature.

			mom_w = sqrt( ( (2./3.) *   f_icept             ) +
			              ( (1./3.) * ( f_icept + f_slope ) )   )
			mom_t = ( (2./3.) * mom_t_per ) + \
			        ( (1./3.) * mom_t_par )

			# Compute the estimate temperature anisotropy ratio.

			mom_r = mom_t_per / mom_t_par

		else :

			mom_w = mean( eta_w )
			mom_t = ( 1.E-3 / const['k_b'] ) * \
			        const['m_p'] * ( 1.E3 * mom_w )**2

			mom_w_per = None
			mom_w_par = None
			mom_t_per = None
			mom_t_par = None
			mom_r     = None


		# Calculate the expected currents based on the results of the
		# (linear) moments analysis.

		mom_cur = tile( 0., [ self.n_alt, self.n_azm, self.n_vel ] )

		if ( aniso ) :
			for t in range( self.n_alt ) :
				for p in range( self.n_azm ) :
					mom_cur[t,p,:] = self.calc_cur_bmx(
					           self.vel_cen, self.vel_wid,
					           self.alt[t], self.azm[t,p],
					           self.mfi_avg_nrm[0],
					           self.mfi_avg_nrm[1],
					           self.mfi_avg_nrm[2],
					           mom_n, mom_v_vec[0],
					           mom_v_vec[1], mom_v_vec[2],
					           mom_w_per, mom_w_par        )
		else :
			for t in range( self.n_alt ) :
				for p in range( self.n_azm ) :
					mom_cur[t,p,:] = self.calc_cur_max(
					           self.vel_cen, self.vel_wid,
					           self.alt[t], self.azm[t,p],
					           mom_n, mom_v_vec[0],
					           mom_v_vec[1], mom_v_vec[2],
					           mom_w                       )


		# Save the "mom_?" and "mom_?_???" values and select "eta_*"
		# arrays.

		self.mom_n = mom_n
		self.mom_v = mom_v
		self.mom_w = mom_w
		self.mom_t = mom_t
		self.mom_r = mom_r

		self.mom_v_vec = mom_v_vec

		self.mom_w_per = mom_w_per
		self.mom_w_par = mom_w_par
		self.mom_t_per = mom_t_per
		self.mom_t_par = mom_t_par

		self.mom_n_eta = n_eta

		self.mom_eta_ind_t = tk_t
		self.mom_eta_ind_p = tk_p

		self.mom_eta_n = eta_n
		self.mom_eta_v = eta_v
		self.mom_eta_w = eta_w
		self.mom_eta_t = eta_t

		self.mom_cur = mom_cur


		# Message the user that the moments analysis has completed.

		self.emit( SIGNAL('janus_mesg'), 'core', 'end', 'mom' )


		# Emit a signal that indicates that the results of the moments
		# analysis have changed.

		self.emit( SIGNAL('janus_chng_mom_res') )


		# Update the initial guess for the non-linear analysis if
		# dynamic updating has been requested.  If it wasn't, make sure
		# that the new results of the moments analysis are being
		# displayed.

		# Note.  No call to "self.auto_nln_sel" is required here.  If
		#        "self.dyn_gss" is "True", then "self.auto_nln_gss"
		#        will call "self.auto_nln_sel" iff "self.dyn_sel" is
		#        also "True".  If "self.dyn_gss" is "False", then
		#        calling "self.auto_nln_sel" is completely unnecessary
		#        as its output would be no different than that from its
		#        last run (since no changes to the initial guess would
		#        have been made since then.
		#
		#        Likewise, no call is needed here to "self.anls_nln"
		#        since "self.suto_nln_gss" will handle this if
		#        necessary.  Again, if "self.dyn_gss" is "False", then
		#        calling "self.anls_nln" is completely unnecessary as
		#        its output would be no different than that from its
		#        last run (since no changes to the inital guess or to
		#        the point selection would have been made since then).

		if ( self.dyn_gss ) :
			self.auto_nln_gss( )
		else :
			self.chng_dsp( 'mom' )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING A NLN SPECIES.
	#-----------------------------------------------------------------------

	def chng_nln_spc( self, s, param, val ) :

		# Ensure that "i" is a valid ion-species index.

		s = int( s )

		if ( ( s < 0 ) or ( s >= self.nln_n_spc ) ) :
			return

		# Change the parameter of the specified ion-species to the
		# specified value.

		if   ( param == 'name' ) :
			try :
				self.nln_pyon.arr_spec[s]['name'] = str( val )
			except :
				self.nln_pyon.arr_spec[s]['name'] = None

		elif ( param == 'sym' ) :
			try :
				self.nln_pyon.arr_spec[s]['sym'] = str( val )
			except :
				self.nln_pyon.arr_spec[s]['sym'] = None

		elif ( param == 'm' ) :
			try :
				val = float( val )
				if ( val >= 0 ) :
					self.nln_pyon.arr_spec[s]['m'] = val
				else :
					self.nln_pyon.arr_spec[s]['m'] = None
			except :
				self.nln_pyon.arr_spec[s]['m'] = None

		elif ( param == 'q' ) :
			try :
				val = float( val )
				if ( val >= 0 ) :
					self.nln_pyon.arr_spec[s]['q'] = val
				else :
					self.nln_pyon.arr_spec[s]['q'] = None
			except :
				self.nln_pyon.arr_spec[s]['q'] = None

		# Propagate the changes to the ion population.

		self.prop_nln_ion( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING A NLN POPULATION.
	#-----------------------------------------------------------------------

	def chng_nln_pop( self, i, param, val ) :

		# Ensure that "i" is a valid ion-population index.

		i = int( i )

		if ( ( i < 0 ) or ( i >= self.nln_n_pop ) ) :
			return

		# Change the parameter of the specified ion-population to the
		# specified value.

		if ( param == 'use' ) :

			self.nln_pop_use[i] = bool( val )

		if ( param == 'spec' ) :

			if ( ( val >= 0              ) and
			     ( val <  self.nln_n_spc )     ) :

				# If the population's name and/or symbol would
				# contradict with a population already
				# associated with the new species, clear out
				# both.

				if ( ( self.nln_pyon.get_pop( 
				          self.nln_pyon.arr_spec[
				                         val]['sym'],
				          self.nln_pyon.arr_pop[
				                           i]['name'] )
				                             is not None) or
				     ( self.nln_pyon.get_pop( 
				          self.nln_pyon.arr_spec[
				                         val]['sym'],
				          self.nln_pyon.arr_pop[
				                           i]['sym']  )
				                             is not None)    ) :

					self.nln_pyon.arr_pop[i]['name'] = None
					self.nln_pyon.arr_pop[i]['sym']  = None

					self.emit( SIGNAL('janus_chng_nln_pop'), i )

				try :
					self.nln_pyon.arr_pop[i]['spec'] = \
					             self.nln_pyon.arr_spec[val]
				except :
					self.nln_pyon.arr_pop[i]['spec'] = None

			else :

				self.nln_pyon.arr_pop[i]['spec'] = None

		if ( param == 'name' ) :

			try :
				self.nln_pyon.arr_pop[i]['name'] = str( val )
			except :
				self.nln_pyon.arr_pop[i]['name'] = None

		if ( param == 'sym' ) :

			try :
				self.nln_pyon.arr_pop[i]['sym'] = str( val )
			except :
				self.nln_pyon.arr_pop[i]['sym'] = None

		if ( param == 'drift' ) :

			try :
				self.nln_pyon.arr_pop[i]['drift'] = bool( val )
			except :
				self.nln_pyon.arr_pop[i]['drift'] = None

		if ( param == 'aniso' ) :

			try :
				self.nln_pyon.arr_pop[i]['aniso'] = bool( val )
			except :
				self.nln_pyon.arr_pop[i]['aniso'] = None

		# Propagate the changes to the ion population.

		self.prop_nln_ion( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR PROPAGATING INFO. ON THE ION SPECIES/POP.'S.
	#-----------------------------------------------------------------------

	def prop_nln_ion( self ) :

		# Record the validity of each ion population.

		for p in range( self.nln_n_pop ) :

			self.nln_pop_vld[p] = \
			     self.nln_pyon.arr_pop[p].valid( require_val=False )

		# Emit a signal that indicates that the ion parameters for the
		# non-linear analysis have changed.

		self.emit( SIGNAL('janus_chng_nln_ion') )

		# If dynamic updating of the initial guess has been enabled, run
		# the automated guess-generator.  Otherwise, skip directly to
		# the function that generates the initial-guess arrays.

		if ( self.dyn_gss ) :
			self.auto_nln_gss( )
		else :
			self.make_nln_gss( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING A SETTING FOR THE NLN ANALYSIS.
	#-----------------------------------------------------------------------

	def chng_nln_set( self, i, param, val ) :

		# Ensure that the arguments are valid.

		if ( ( i < 0 ) or ( i >= self.nln_n_pop ) ) :
			return

		# Change the parameter(s) of the specified ion species to the
		# specified values.

		if   ( param == 'gss_n' ) :

			try :
				self.nln_set_gss_n[i] = float( val )
			except :
				self.nln_set_gss_n[i] = None

			if ( ( self.nln_set_gss_n[i] is not None ) and
			     ( self.nln_set_gss_n[i] <= 0        )     ) :
				self.nln_set_gss_n[i] = None

		elif ( param == 'gss_d' ) :

			try :
				self.nln_set_gss_d[i] = float( val )
			except :
				self.nln_set_gss_d[i] = None

		elif ( param == 'gss_w' ) :

			try :
				self.nln_set_gss_w[i] = float( val )
			except :
				self.nln_set_gss_w[i] = None

			if ( ( self.nln_set_gss_w[i] is not None ) and
			     ( self.nln_set_gss_w[i] <= 0        )     ) :
				self.nln_set_gss_w[i] = None

		elif ( param == 'sel' ) :

			try :
				self.nln_set_sel_a[i] = float( val[0] )
			except :
				self.nln_set_sel_a[i] = None

			try :
				self.nln_set_sel_b[i] = float( val[1] )
			except :
				self.nln_set_sel_b[i] = None

			if ( ( self.nln_set_sel_a[i] is not None       ) and
			     ( self.nln_set_sel_b[i] is not None       ) and
			     ( self.nln_set_sel_a[i]
			                      >= self.nln_set_sel_b[i] )     ) :
				self.nln_set_sel_a[i] = None
				self.nln_set_sel_b[i] = None

		else :

			return

		# Validate the settings for the specified ion population.

		if   ( ( self.nln_set_gss_n[i] is None ) or
		       ( self.nln_set_gss_w[i] is None )    ) :
			self.nln_set_gss_vld[i] = False
		elif ( ( self.nln_pyon.arr_pop[i]['drift'] ) and
		       ( self.nln_set_gss_d[i] is None     )     ) :
			self.nln_set_gss_vld[i] = False
		else :
			self.nln_set_gss_vld[i] = True

		if ( ( self.nln_set_sel_a[i] is None ) or
		     ( self.nln_set_sel_b[i] is None )    ) :
			self.nln_set_sel_vld[i] = False
		else :
			self.nln_set_sel_vld[i] = True

		# Propagate the changes to the settings for the non-linear
		# analysis.

		self.prop_nln_set( param[0:3] )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR PROPAGATING THE SETTINGS FOR THE NLN ANALYSIS.
	#-----------------------------------------------------------------------

	def prop_nln_set( self, chng ) :

		# Emit a signal that indicates that the settings for the
		# non-linear analysis have changed.

		self.emit( SIGNAL('janus_chng_nln_set') )

		# Regenerate the initial guess or data selection.

		# Note.  The functions called should make any necessay updates
		#        to the dynamic variables.

		if   ( chng == 'gss' ) :
			self.auto_nln_gss( )
		elif ( chng == 'sel' ) :
			self.auto_nln_sel( )
		else :
			return

		# If the above call of "auto_nln_???" did not cause the
		# non-linear fitting to be run, make sure that the initial guess
		# and data selection are being displayed.

		if ( not self.dyn_nln ) :
			self.chng_dsp( "gsl" )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR AUTO-GENERATING THE INITIAL GUESS FOR NLN.
	#-----------------------------------------------------------------------

	def auto_nln_gss( self ) :

		# Assume that, in calling this function, the user would like
		# futher adjustments to the initial guess to be automatic; i.e.,
		# enable dynamic generation of the initial guess.

		self.chng_dyn( 'gss', True, rerun=False )

		# Reset all variables associated with the initial guess.

		self.rset_var( var_nln_gss=True )

		# If the moments analysis does not seem to have been run
		# (sucessfully), run the "make_nln_gss" function (to update the
		# "self.nln_gss_" arrays, widgets, etc.) and then abort.

		if ( self.mom_n is None ) :

			self.make_nln_gss( )

			return

		# Attempt to generate an initial guess of the bulk velocity (of
		# non-drifting species).

		try :
			self.nln_pyon['v0_x'] = round( self.mom_v_vec[0], 1 )
			self.nln_pyon['v0_y'] = round( self.mom_v_vec[1], 1 )
			self.nln_pyon['v0_z'] = round( self.mom_v_vec[2], 1 )
		except :
			self.nln_pyon['v0_x'] = None
			self.nln_pyon['v0_y'] = None
			self.nln_pyon['v0_z'] = None

		# Attempt to generate an initial guess of the parameters for
		# each ion population.

		for i in range( self.nln_n_pop ) :

			# If the ion population is not in use, is invalid, or
			# has invalid guess-settings, cotinue on to the next
			# one.

			if ( ( not self.nln_pop_use[i]     ) or
			     ( not self.nln_pop_vld[i]     ) or
			     ( not self.nln_set_gss_vld[i] )    ) :
				continue

			# Generate the initial guess for this population's
			# density.

			try :
				self.nln_pyon.arr_pop[i]['n'] = round_sig(
				         self.nln_set_gss_n[i] * self.mom_n, 4 )
			except :
				self.nln_pyon.arr_pop[i]['n'] = None

			# Generate (if necessary) the initial guess for this
			# population's differential flow.

			if ( self.nln_pyon.arr_pop[i]['drift'] ) :
				try :
					sgn = sign( dot( self.mom_v_vec,
					                 self.mfi_avg_nrm ) )
					if ( sgn == 0. ) :
						sgn = 1.
					self.nln_pyon.arr_pop[i]['dv'] = \
					    round_sig(
					        sgn * self.mom_v
					            * self.nln_set_gss_d[i], 4 )
				except :
					self.nln_pyon.arr_pop[i]['dv'] = None

			# Generate the initial guess of this population's
			# thermal speed(s).

			if ( self.nln_pyon.arr_pop[i]['aniso'] ) :
				try :
					self.nln_pyon.arr_pop[i]['w_per'] = \
					   round_sig( self.nln_set_gss_w[i]
					                       * self.mom_w, 4 )
				except :
					self.nln_pyon.arr_pop[i]['w_per'] = \
					      None
				try :
					self.nln_pyon.arr_pop[i]['w_par'] = \
					   round_sig( self.nln_set_gss_w[i]
					                       * self.mom_w, 4 )
				except :
					self.nln_pyon.arr_pop[i]['w_par'] = \
					      None
			else :
				try :
					self.nln_pyon.arr_pop[i]['w'] = \
					   round_sig( self.nln_set_gss_w[i]
					                       * self.mom_w, 4 )
				except :
					self.nln_pyon.arr_pop[i]['w'] = \
					      None

		# Run the "make_nln_gss" function to update the "self.nln_gss_"
		# arrays, widgets, etc.

		self.make_nln_gss( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING A GUESS VALUE FOR ONE NLN PARAMETER.
	#-----------------------------------------------------------------------

	def chng_nln_gss( self, i, param, val ) :

		# Assume that, in calling this function, the user would like
		# futher adjustments to the initial guess to be manual; i.e.,
		# disable dynamic generation of an automatic initial-guess.

		self.chng_dyn( 'gss', False, rerun=False )

		# Ensure that the argument "p" is a valid population (unless
		# the "param" argument indicates a velocity component, in which
		# case "p" is irrelevant).

		if ( ( param != 'v_x' ) and
		     ( param != 'v_y' ) and ( param != 'v_z' ) ) :

			if ( ( i < 0 ) or ( i >= self.nln_n_pop ) ) :
				return

		# Change the requested parameter of the requested ion population
		# to the requested value.

		# Note.  Simply "pass"-ing in the event of an "except"-ion
		#        should be sufficient.  If the "pyon" class raises an
		#        "except"-ion during an assignment, it should set the
		#        parameter in question equal to "None".

		if   ( param == 'v_x' ) :

			try :
				self.nln_pyon['v0_x'] = val
			except :
				self.nln_pyon['v0_x'] = None

		elif ( param == 'v_y' ) :

			try :
				self.nln_pyon['v0_y'] = val
			except :
				self.nln_pyon['v0_y'] = None

		elif ( param == 'v_z' ) :

			try :
				self.nln_pyon['v0_z'] = val
			except :
				self.nln_pyon['v0_z'] = None

		elif ( param == 'n' ) :

			try :
				self.nln_pyon.arr_pop[i]['n'] = val
			except :
				self.nln_pyon.arr_pop[i]['n'] = None

		elif ( param == 'dv' ) :

			try :
				self.nln_pyon.arr_pop[i]['dv'] = val
			except :
				self.nln_pyon.arr_pop[i]['dv'] = None

		elif ( param == 'w' ) :

			try :
				self.nln_pyon.arr_pop[i]['w'] = val
			except :
				self.nln_pyon.arr_pop[i]['w'] = None

		elif ( param == 'w_per' ) :

			try :
				self.nln_pyon.arr_pop[i]['w_per'] = val
			except :
				self.nln_pyon.arr_pop[i]['w_per'] = None

		elif ( param == 'w_par' ) :

			try :
				self.nln_pyon.arr_pop[i]['w_par'] = val
			except :
				self.nln_pyon.arr_pop[i]['w_par'] = None

		# Run the "make_nln_gss" function to update the "self.nln_gss_"
		# arrays, widgets, etc.

		self.make_nln_gss( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR MAKING THE NLN INITIAL GUESS PARAMETER ARRAY.
	#-----------------------------------------------------------------------

	def make_nln_gss( self ) :

		# Establish which of the ion populations are in use, are valid,
		# and have initial guesses.

		for i in range ( self.nln_n_pop ) :

			if ( ( self.nln_pop_use[i]               ) and
			     ( self.nln_pop_vld[i]               ) and
			     ( self.nln_pyon.arr_pop[i].valid(
			                      require_val=True ) )     ) :

				self.nln_gss_vld[i] = True

			else :

				self.nln_gss_vld[i] = False

		self.nln_gss_pop = where( self.nln_gss_vld )[0]

		# Reset the "prm" and "cur_???" arrays.

		self.nln_gss_prm = array( [] )

		self.nln_gss_cur_ion = None
		self.nln_gss_cur_tot = None

		# Abort if any of the following cases are arise:
		#   -- No populations have been found to be valid.
		#   -- The primary population is not valid.
		#   -- The init. guess of any reference vel. comp. is invalid.
		#   -- No magnetic field data was loaded.
		# To abort, take the following actions:
		#   -- Emit the signal that the NLN guess has been updated.
		#   -- Return.

		if ( ( len( self.nln_gss_pop ) == 0    ) or
		     ( 0 not in self.nln_gss_pop       ) or
		     ( None in self.nln_pyon['vec_v0'] ) or
		     ( self.n_mfi == 0                 )    ) :

			self.emit( SIGNAL('janus_chng_nln_gss') )

			return

		# Generate the intial guess array in the format expected.

		prm = list( self.nln_pyon['vec_v0'] )

		for i in self.nln_gss_pop :

			prm.append( self.nln_pyon.arr_pop[i]['n'] )

			if ( self.nln_pyon.arr_pop[i]['drift'] ) :
				prm.append( self.nln_pyon.arr_pop[i]['dv'] )

			if ( self.nln_pyon.arr_pop[i]['aniso'] ) :
				prm.append( self.nln_pyon.arr_pop[i]['w_per'] )
				prm.append( self.nln_pyon.arr_pop[i]['w_par'] )
			else :
				prm.append( self.nln_pyon.arr_pop[i]['w'] )

		self.nln_gss_prm = array( prm )

		# Calculate the expected currents based on the initial geuss.

		# FIXME: This code (and that in "self.calc_nln_cur") may not be
		#        especially efficient.

		( tk_t, tk_p, tk_v ) = indices( ( self.n_alt, self.n_azm,
		                                  self.n_vel              ) )

		tk_t = tk_t.flatten( )
		tk_p = tk_p.flatten( )
		tk_v = tk_v.flatten( )

		x_vel_cen = self.vel_cen[ tk_v ]
		x_vel_wid = self.vel_wid[ tk_v ]
		x_alt     = self.alt[ tk_t ]
		x_azm     = self.azm[ tk_t, tk_p ]
		x_mag_x   = self.mag_x[ tk_v ]
		x_mag_y   = self.mag_y[ tk_v ]
		x_mag_z   = self.mag_z[ tk_v ]

		x = array( [ x_vel_cen, x_vel_wid, x_alt, x_azm,
		             x_mag_x, x_mag_y, x_mag_z           ] )

		self.nln_gss_cur_ion = reshape(
		      self.calc_nln_cur( self.nln_gss_pop, x,
		                         self.nln_gss_prm,
		                         ret_comp=True        ),
		      ( self.n_alt, self.n_azm, self.n_vel,
		        len( self.nln_gss_pop )             )    )

		self.nln_gss_cur_tot = sum( self.nln_gss_cur_ion, axis=3 )

		# Propagate the new initial-guess for the non-linear analysis.

		self.prop_nln_gss( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR PROPAGATING THE GUESS FOR THE NLN ANALYSIS.
	#-----------------------------------------------------------------------

	def prop_nln_gss( self ) :

		# Emit a signal that indicates that the initial guess for the
		# non-linear analysis has changed.

		self.emit( SIGNAL('janus_chng_nln_gss') )

		# If warranted (based on the values of "self.dyn_???"), proceed
		# with dynamic updates to the non-linear analysis.  Otherwise,
		# make sure that the initial guess is being displayed.

		if ( self.dyn_sel ) :
			self.auto_nln_sel( )
		elif ( self.dyn_nln ) :
			self.anls_nln( )
		else :
			self.chng_dsp( 'gsl' )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR AUTOMATIC DATA SELECT. FOR THE NON-LIN. ANAL.
	#-----------------------------------------------------------------------

	def auto_nln_sel( self ) :

		# Assume that, in calling this function, the user would like
		# futher adjustments to the point selection to be automatic;
		# i.e., enable dynamic point selection.

		self.chng_dyn( 'sel', True, rerun=False )

		# Re-initialize the data-selection variables for the non-linear
		# analysis.

		self.rset_var( var_nln_sel=True )

		# Intially deselect all data.

		self.nln_sel = tile( False, [ self.n_alt, self.n_azm,
		                              self.n_vel              ] )

		# Determine which ion species have been selected for analysis
		# and have been given valid parameters, initial geusses, and
		# selection windows.

		pop = where( ( self.nln_gss_vld     ) &
		             ( self.nln_set_sel_vld )   )[0]

		# If point selection canott be run for any ion population or no
		# magentic-field data are available for this spectrum, run the
		# validation code (to update the registered widgets, etc.) and
		# abort.

		if ( ( len( pop ) == 0 ) or
		     ( self.n_mfi == 0 )    ) :

			self.vldt_nln_sel( )

			return

		# Select data based on the selection windows from each of the
		# look directions selected for the moments analysis.

		( tk_t, tk_p ) = where( self.mom_sel_azm )

		n_tk = len( tk_t )

		for j in range( n_tk ) :

			# Extract the current look direction and convert it
			# from altitude-azimuth to rectangular coordiantes.

			t = tk_t[j]
			p = tk_p[j]

			alt = self.alt[t]
			azm = self.azm[t,p]

			dlk = self.calc_dir_look( alt, azm )

			# Select data for each species.

			for i in pop :

				# Extract the estimated bulk velocity (and the
				# magnitude thereof) of this ion species (based
				# on the initial guess).

				vel = array( self.nln_pyon['vec_v0'] )

				if ( self.nln_pyon.arr_pop[i]['drift'] ) :
					vel += self.mfi_avg_nrm * \
					          self.nln_pyon.arr_pop[i]['dv']

				v = sqrt( vel[0]**2 + vel[1]**2 + vel[2]**2 )

				# Compute the negative of the projected bulk
				# velocity along the look direction.

				v_proj = - dot( vel, dlk )

				# Compute the range of projected inflow speeds
				# specified by this ion species' charge-to-mass
				# ratio, initial geusses, and selection window.

				if ( self.nln_pyon.arr_pop[i]['aniso'] ) :
					ang = abs( dot( dlk, self.mfi_avg_nrm ))
					w = sqrt(
					   ( self.nln_pyon.arr_pop[i]['w_per']
					                     * sin(ang) )**2 +
					   ( self.nln_pyon.arr_pop[i]['w_par']
					                     * cos(ang) )**2   )
				else :
					w = self.nln_pyon.arr_pop[i]['w']

				v_min = v_proj + ( self.nln_set_sel_a[i] *
				                   w * v_proj / v          )
				v_max = v_proj + ( self.nln_set_sel_b[i] *
				                   w * v_proj / v          )

				v_min = v_min * sqrt(
				               self.nln_pyon.arr_pop[i]['m'] /
				               self.nln_pyon.arr_pop[i]['q']   )
				v_max = v_max * sqrt(
				               self.nln_pyon.arr_pop[i]['m'] /
				               self.nln_pyon.arr_pop[i]['q']   )

				# Select all seemingly valid measurements from
				# this look direction that fall into this range
				# range of inflow speeds.

				tk = where( ( self.cur_vld[t,p,:]   ) &
				            ( self.vel_cen >= v_min ) &
				            ( self.vel_cen <= v_max )   )[0]

				if ( len( tk ) > 0 ) :
					self.nln_sel[t,p,tk] = True

		# Propagate the new data-selection for the non-linear analysis.

		self.prop_nln_sel( )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING THE SELECTION OF A SINGLE POINT.
	#-----------------------------------------------------------------------

	def chng_nln_sel( self, t, p, v ) :

		# As this function was mostly likely called in response to the
		# user manually adjusting the point selection for the
		# non-linear analysis, disable the dynamic updating of this
		# point selection.

		self.chng_dyn( 'sel', False, rerun=False )

		# If necessary, initialize the selection array.

		if ( self.nln_sel is None ) :
			self.nln_sel = tile( False,
			                     [ self.n_alt, self.n_azm,
			                       self.n_vel              ] )

		# Change the selection of the requested point.

		self.nln_sel[t,p,v] = not self.nln_sel[t,p,v]

		# Propagate the new data-selection for the non-linear analysis.

		self.prop_nln_sel( pnt=[t,p,v] )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR PROPAGATING THE NLN DATA-SELECTION.
	#-----------------------------------------------------------------------

	def prop_nln_sel( self, pnt=None ) :

		# Update the count of selected data.

		self.nln_n_sel = len( where( self.nln_sel )[0] )

		# Emit a signal that indicates that the data-selection for the
		# non-linear analysis has changed.

		if ( pnt is None ) :
			self.emit( SIGNAL('janus_chng_nln_sel_all') )
		else :
			self.emit( SIGNAL('janus_chng_nln_sel_cur'),
			           pnt[0], pnt[1], pnt[2]            )

		# If dynamic updating of the non-linear fitting has been
		# enabled, run it.  Otherwise, make sure that the initial guess
		# and data selection are being displayed.

		if ( self.dyn_nln ) :
			self.anls_nln( )
		else :
			self.chng_dsp( 'gsl' )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CALCULATING THE NLN MODEL CURRNET.
	#-----------------------------------------------------------------------

	def calc_nln_cur( self, pop, x, prm, ret_comp=False ) :

		# Extract the independent data variables (i.e., the
		# specifications of the velocity windows and pointing
		# directions).

		d_vel_cen = x[0]
		d_vel_wid = x[1]
		d_alt     = x[2]
		d_azm     = x[3]
		d_mag_x   = x[4]
		d_mag_y   = x[5]
		d_mag_z   = x[6]

		# Compute the normalized magnetic field values.

		d_mag = sqrt( d_mag_x**2 + d_mag_y**2 + d_mag_z**2 )

		d_nrm_x = d_mag_x / d_mag
		d_nrm_y = d_mag_y / d_mag
		d_nrm_z = d_mag_z / d_mag

		# For each ion species, extract the passed parameters and
		# calculate it's contribution to the total current.

		if hasattr( x[0], '__iter__' ) :
			cur = tile( 0., [ len( x[0] ), self.nln_n_pop ] )
		else :
			cur = tile( 0., self.nln_n_pop )

		prm_v0_x = prm[0]
		prm_v0_y = prm[1]
		prm_v0_z = prm[2]

		c = 3

		for p in pop :

			# Extract the density of population "p".

			prm_n = prm[c]

			c += 1

			# Determine the bulk velocity of population "p",
			# extracting (if necessary) the population's drift.

			if ( self.nln_pyon.arr_pop[p]['drift'] ) :

				prm_dv = prm[c]

				c += 1

				prm_v_x = prm_v0_x + ( prm_dv * d_nrm_x )
				prm_v_y = prm_v0_y + ( prm_dv * d_nrm_y )
				prm_v_z = prm_v0_z + ( prm_dv * d_nrm_z )

			else :

				prm_v_x = prm_v0_x
				prm_v_y = prm_v0_y
				prm_v_z = prm_v0_z

			# Extract the thermal speed(s).

			if ( self.nln_pyon.arr_pop[p]['aniso'] ) :

				prm_w_per = prm[c  ]
				prm_w_par = prm[c+1]

				c += 2

			else :

				prm_w = prm[c]

				c += 1

			# Add the contribution of this ion species to
			# the total current.

			sqm = sqrt( self.nln_pyon.arr_pop[p]['q'] /
			            self.nln_pyon.arr_pop[p]['m']   )

			if ( self.nln_pyon.arr_pop[p]['aniso'] ) :
				cur_p = self.nln_pyon.arr_pop[p]['q'] * \
				        self.calc_cur_bmx(
					            d_vel_cen * sqm,
					            d_vel_wid * sqm,
				                    d_alt, d_azm,
					            d_nrm_x, d_nrm_y, d_nrm_z,
				                    prm_n, prm_v_x,
				                    prm_v_y, prm_v_z,
				                    prm_w_per, prm_w_par       )
			else :
				cur_p = self.nln_pyon.arr_pop[p]['q'] * \
				        self.calc_cur_max( d_vel_cen * sqm,
					                   d_vel_wid * sqm,
				                           d_alt, d_azm,
				                           prm_n, prm_v_x,
				                           prm_v_y, prm_v_z,
				                           prm_w             )

			if hasattr( x[0], '__iter__' ) :
				cur[:,p] = cur_p
			else :
				cur[p] = cur_p

		# Return the total current from all modeled ion species.

		if hasattr( x[0], '__iter__' ) :
			if ( ret_comp ) :
				return cur[:,pop]
			else :
				return sum( cur, axis=1 )
		else :
			if ( ret_comp ) :
				return cur[pop]
			else :
				return sum( cur, axis=0 )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR RUNNING THE NON-LINEAR ANALYSIS.
	#-----------------------------------------------------------------------

	def anls_nln( self ) :

		# Re-initialize the output of the non-linear analysis.

		self.rset_var( var_nln_res=True )

		# Load the list of ion populations to be analyzed and the intial
		# guess of their parameters.

		pop = self.nln_gss_pop
		gss = self.nln_gss_prm

		# If any of the following conditions are met, emit a signal that
		# indicates that the results of the non-linear analysis have
		# change, and abort.
		#   -- No ion spectrum has been loaded.
		#   -- No ion population is available for analysis.
		#   -- The primary ion species is not available for analysis.
		#   -- No initial guess has been generated.
		#   -- Insufficient data have been selected.

		if ( ( self.n_vel == 0                   ) or
		     ( self.n_mfi == 0                   ) or
		     ( len( pop ) == 0                   ) or
		     ( 0 not in pop                      ) or
		     ( len( gss ) == 0                   ) or
		     ( self.nln_n_sel < self.nln_min_sel )    ) :

			self.emit( SIGNAL('janus_mesg'),
			           'core', 'norun', 'nln' )

			self.emit( SIGNAL('janus_chng_nln_res') )

			return

		# Message the user that the non-linear analysis has begun.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'nln' )

		# Define the function for evaluating the modeled current.

		def model( x, *p ) :

			return self.calc_nln_cur( pop, x, array( p ) )

		# Save the data selection and then use it to generate data
		# arrays for the non-linear fit.

		self.nln_res_sel = self.nln_sel.copy( )

		( tk_t, tk_p, tk_v ) = where( self.nln_res_sel )

		x_vel_cen = self.vel_cen[ tk_v ]
		x_vel_wid = self.vel_wid[ tk_v ]
		x_alt     = self.alt[ tk_t ]
		x_azm     = self.azm[ tk_t, tk_p ]
		x_mag_x   = self.mag_x[ tk_v ]
		x_mag_y   = self.mag_y[ tk_v ]
		x_mag_z   = self.mag_z[ tk_v ]

		x = array( [ x_vel_cen, x_vel_wid, x_alt, x_azm,
		             x_mag_x, x_mag_y, x_mag_z           ] )

		y = self.cur[ tk_t, tk_p, tk_v ]

		# Attempt to perform the non-linear fit.  If this fails, reset
		# the associated variables and abort.

		try :

			( fit, covar ) = curve_fit( model, x, y, gss,
			                            sigma=sqrt(y)     )

			sigma = sqrt( diag( covar ) )

		except :

			self.emit( SIGNAL('janus_mesg'), 'core', 'fail', 'nln' )

			self.rset_var( var_nln_res=True )

			self.emit( SIGNAL('janus_chng_nln_res') )

			return

		# Calculate the expected currents based on the results of the
		# non-linear analysis.

		( tk_t, tk_p, tk_v ) = indices( ( self.n_alt, self.n_azm,
		                                  self.n_vel              ) )

		tk_t = tk_t.flatten( )
		tk_p = tk_p.flatten( )
		tk_v = tk_v.flatten( )

		x_vel_cen = self.vel_cen[ tk_v ]
		x_vel_wid = self.vel_wid[ tk_v ]
		x_alt     = self.alt[ tk_t ]
		x_azm     = self.azm[ tk_t, tk_p ]
		x_mag_x   = self.mag_x[ tk_v ]
		x_mag_y   = self.mag_y[ tk_v ]
		x_mag_z   = self.mag_z[ tk_v ]

		x = array( [ x_vel_cen, x_vel_wid, x_alt, x_azm,
		             x_mag_x, x_mag_y, x_mag_z           ] )

		self.nln_res_cur_ion = \
		   reshape( self.calc_nln_cur( pop, x, fit, ret_comp=True ),
		            ( self.n_alt, self.n_azm, self.n_vel, len( pop ) ) )

		self.nln_res_cur_tot = sum( self.nln_res_cur_ion, axis=3 )

		# Save the properties and fit parameters for each ion species
		# used in this analysis.

		self.nln_res_plas.covar = covar.copy( )

		self.nln_res_plas['time'] = self.time_epc

		self.nln_res_plas['b0_x'] = self.mfi_avg_vec[0]
		self.nln_res_plas['b0_y'] = self.mfi_avg_vec[1]
		self.nln_res_plas['b0_z'] = self.mfi_avg_vec[2]

		self.nln_res_plas['v0_x'] = fit[0]
		self.nln_res_plas['v0_y'] = fit[1]
		self.nln_res_plas['v0_z'] = fit[2]
		self.nln_res_plas['sig_v0_x'] = sigma[0]
		self.nln_res_plas['sig_v0_y'] = sigma[1]
		self.nln_res_plas['sig_v0_z'] = sigma[2]
		c = 3

		for i in pop :

			# If necessary, add this population's species to the
			# results.

			spc_name = self.nln_pyon.arr_pop[i].my_spec['name']

			if ( self.nln_res_plas.get_spec( spc_name ) is None ) :

				spc_sym = \
				         self.nln_pyon.arr_pop[i].my_spec['sym']
				spc_m   = \
				         self.nln_pyon.arr_pop[i].my_spec['m'  ]
				spc_q   = \
				         self.nln_pyon.arr_pop[i].my_spec['q'  ]

				self.nln_res_plas.add_spec(
				                   name=spc_name, sym=spc_sym,
				                   m=spc_m, q=spc_q            )

			# Add the population itself to the results.

			pop_drift = self.nln_pyon.arr_pop[i]['drift']
			pop_aniso = self.nln_pyon.arr_pop[i]['aniso']
			pop_name  = self.nln_pyon.arr_pop[i]['name']
			pop_sym   = self.nln_pyon.arr_pop[i]['sym']

			pop_n   = fit[c]
			pop_sig_n = sigma[c]
			c += 1

			if ( pop_drift ) :
				pop_dv = fit[c]
				pop_sig_dv = sigma[c]
				c += 1
			else :
				pop_dv = None
				pop_sig_dv = None

			if ( pop_aniso ) :
				pop_w     = None
				pop_w_per = fit[c  ]
				pop_w_par = fit[c+1]
				pop_sig_w     = None
				pop_sig_w_per = sigma[c  ]
				pop_sig_w_par = sigma[c+1]
				c += 2
			else :
				pop_w     = fit[c]
				pop_w_per = None
				pop_w_par = None
				pop_sig_w     = sigma[c]
				pop_sig_w_per = None
				pop_sig_w_par = None
				c += 1

			self.nln_res_plas.add_pop(
			       spc=spc_name, drift=pop_drift, aniso=pop_aniso,
			       name=pop_name, sym=pop_sym, n=pop_n, dv=pop_dv,
			       w=pop_w, w_per=pop_w_per, w_par=pop_w_par,
			       sig_n=pop_sig_n, sig_dv=pop_sig_dv, sig_w=pop_sig_w,
			       sig_w_per=pop_sig_w_per, sig_w_par=pop_sig_w_par        )

		# Save the results of the this non-linear analysis to the
		# results log.

		self.series.add_spec( self.nln_res_plas )

		# Message the user that the non-linear analysis has finished.

		self.emit( SIGNAL('janus_mesg'), 'core', 'end', 'nln' )

		# Emit a signal that indicates that the results of the
		# non-linear analysis have changed.

		self.emit( SIGNAL('janus_chng_nln_res') )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING THE DISPLAYED ANALYSIS.
	#-----------------------------------------------------------------------

	def chng_dsp( self, value ) :

		# If "self.dsp" already equals "value," abort (without any
		# notice to the registered widgets) as nothing needs to be done.

		if ( self.dsp == value ) :

			return

		# If "value" is a valid display setting, update the value of
		# "self.dsp"; otherwise, set "self.dsp" to "None".

		if ( ( value == 'mom' ) or ( value == 'gsl' ) or
		     ( value == 'nln' )                          ) :

			self.dsp = value

		else :

			self.dsp = None

		# Emit a signal that indicates that the "display" setting has
		# changed.

		self.emit( SIGNAL('janus_chng_dsp') )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR CHANGING IF AN ANALYSIS UPDATES DYNAMICALLY.
	#-----------------------------------------------------------------------

	def chng_dyn( self, anal, value, rerun=True ) :

		# Regularize "value" to ensure that it is a standard boolean.

		value = True if ( value ) else False

		# Based on "anal", update the appropriate "self.dyn_???".  If no
		# change is necessary, return (i.e., without requesting that the
		# widgets update).

		if ( anal == 'mom' ) :

			if ( self.dyn_mom != value ) :
				self.dyn_mom = value
			else :
				return

		elif ( anal == 'gss' ) :

			if ( self.dyn_gss != value ) :
				self.dyn_gss = value
			else :
				return

		elif ( anal == 'sel' ) :

			if ( self.dyn_sel != value ) :
				self.dyn_sel = value
			else :
				return

		elif ( anal == 'nln' ) :

			if ( self.dyn_nln != value ) :
				self.dyn_nln = value
			else :
				return

		else :

			return

		# Emit a signal that indicates that the "dynamic" settings have
		# changed.

		self.emit( SIGNAL('janus_chng_dyn') )

		# If dynamic updates has been turned on for the specified
		# analysis "anal", and the user hasn't requested otherwise,
		# re-run that analysis and adjust the display.

		if ( ( value ) and ( rerun ) ) :

			if ( anal == 'mom' ) :

				self.anls_mom( )

				if ( ( not self.dyn_sel ) and
				     ( not self.dyn_gss )     ) :
					self.chng_dsp( 'mom' )
				elif ( self.dyn_nln ) :
					self.chng_dsp( 'nln' )
				else :
					self.chng_dsp( 'gsl' )

			elif ( anal == 'gss' ) :

				self.auto_nln_gss( )

				if ( self.dyn_nln ) :
					self.chng_dsp( 'nln' )
				else :
					self.chng_dsp( 'gsl' )

			elif ( anal == 'sel' ) :

				self.auto_nln_sel( )

				if ( self.dyn_nln ) :
					self.chng_dsp( 'nln' )
				else :
					self.chng_dsp( 'gsl' )

			elif ( anal == 'nln' ) :

				self.anls_nln( )

				self.chng_dsp( 'nln' )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR AUTOMATICALLY RUNNING A RANGE OF SPECTRA.
	#-----------------------------------------------------------------------

	def auto_run( self, t_strt, t_stop,
	                    get_next=None, err_halt=None, pause=None ) :

		# Supply values for any missing keywords.

		get_next = False if ( get_next is None ) else get_next
		err_halt = False if ( err_halt is None ) else err_halt
		pause    = 0     if ( pause    is None ) else pause

		# Message the user that the automated analysis is about to
		# begin.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'auto' )

		# Attempt to convert the start and stop timestamps to epoch
		# times.  If one or more fails, or if the start time does not
		# strictly precede the stop time, abort.

		time_strt = calc_time_epc( t_strt )
		time_stop = calc_time_epc( t_stop )

		if ( ( time_strt is None ) or ( time_stop is None ) ) :
			return
		elif ( time_strt >= time_stop ) :
			return

		# Begin with the start time stamp.  Load and process spectra,
		# one by one, until the stop timestamp is reached (or a
		# premature stop has been requested).

		first_pass = True
		self.stop_auto_run = False

		while ( not self.stop_auto_run ) :

			# Load and analyze (according to the "self.dyn_???"
			# parameters) the first/next spectrum.

			if ( first_pass ) :
				first_pass = False
				self.load_spec( time_req=time_strt,
				                get_next=get_next   )
			else :
				self.load_spec( time_req=self.time_epc,
				                get_next=True           )

			# If no spectrum was able to be loaded, abort.

			if ( self.time_epc is None ) :
				self.stop_auto_run = True
				break

			# If requested by the user, check for errors from the
			# analyses that were run.  If any are found, abort.

			if ( err_halt ) :
				if ( self.n_mfi == 0 ) :
					self.stop_auto_run = True
					break
				if ( ( self.dyn_mom       ) and
				     ( self.mom_n is None )     ) :
					self.stop_auto_run = True
					break
				if ( ( self.dyn_nln               ) and
				     ( self.nln_res_ion_n is None )     ) :
					self.stop_auto_run = True
					break

			# If the spectrum just loaded was the last that needed
			# to be loaded, end.

			if ( self.time_epc > time_stop ) :
				break

			# If a request to abort has come from some source other
			# than this function (e.g., a user), do so.  Otherwise,
			# wait the specified period of time.

			if ( self.stop_auto_run ) :
				break
			else :
				sleep( pause )

		# Message the user that the automated analysis has finished.

		if ( self.stop_auto_run ) :
			self.emit( SIGNAL('janus_mesg'),
			           'core', 'abort', 'auto' )
		else :
			self.emit( SIGNAL('janus_mesg'),
			           'core', 'end'  , 'auto' )

		# Emit a signal that indicates that the automated analysis has
		# ended.

		self.emit( SIGNAL('janus_done_auto_run') )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR SAVING THE RESULTS LOG TO A FILE.
	#-----------------------------------------------------------------------

	def save_res( self, nm_fl, exit=False ) :

		# Message the user that a save is about to begin.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'save' )

		# Try to create a new output file to hold the log of analysis
		# results.  If this fails, message the user and abort.

		try :
			fl = open( nm_fl, 'wb' )
		except :
			self.emit( SIGNAL('janus_mesg'),
			           'core', 'fail', 'save' )

		# Save the results log to the output file.

		pickle.dump( self.series, fl )

		# Close the output file.

		fl.close( )

		# Message the user that the save was successful.

		self.emit( SIGNAL('janus_mesg'), 'core', 'end', 'save' )

		# If requested, exit the application.

		if ( exit ) :
			self.emit( SIGNAL('janus_exit') )

	#-----------------------------------------------------------------------
	# DEFINE THE FUNCTION FOR EXPORTING THE RESULTS TO A TEXT FILE.
	#-----------------------------------------------------------------------

	def xprt_res( self, nm_fl, exit=False ) :

		# Message the user that an export is about to begin.

		self.emit( SIGNAL('janus_mesg'), 'core', 'begin', 'xprt' )

		# Try to create a new output file to hold the log of analysis
		# results in plain text.  If this fails, message the user and
		# abort.

		try :
			fl = open( nm_fl, 'w' )
		except :
			self.emit( SIGNAL('janus_mesg'),
			           'core', 'fail', 'xprt' )

		# Define the format for numerical quantities.

		txt_num = ' {:+10.4e}'
		txt_spc = 11 * ' '
		txt_sep = ( '#-----------------------------' +
		            '-----------------------------'    )

		# Write a header.

		fl.write( txt_sep )
		fl.write( '\n' )
		fl.write( '# Janus Version ' )
		fl.write( self.version )
		fl.write( '\n' )
		fl.write( txt_sep )
		fl.write( '\n' )
		fl.write( '# Comments:\n' )
		fl.write( '#   -- Timestamps are in the format\n'              )
		fl.write( '#      "YYYY-MM-DD/HH-MM-SS" and given in UTC.\n'   )
		fl.write( '#   -- Numerical quantities (except timestamps)\n'  )
		fl.write( '#      are in the format "+10.4e".\n'               )
		fl.write( '#   -- The mass and charge of a species appear\n'   )
		fl.write( '#      (in that order) on the line immediately\n'   )
		fl.write( '#      below that with its name.  These quanties\n' )
		fl.write( '#      are scaled to those for the proton.\n'       )
		fl.write( '#   -- The drift velocity is parallel to the \n'    )
		fl.write( '#      to the magnetic field.  A population with\n' )
		fl.write( '#      no differential flow listed was assumed\n'   )
		fl.write( '#      to not drift (relative to the bulk\n'        )
		fl.write( '#      velocity.)\n'                                )
		fl.write( '#   -- Three values are given for each velocity\n'  )
		fl.write( '#      and magnetic field; these, respecitively,\n' )
		fl.write( '#      are the "x"-, "y"-, and "z"-components in\n' )
		fl.write( '#      the GSE coordinate system.\n'                )
		fl.write( '#   -- Where two quantities are listed for\n'       )
		fl.write( '#      thermal speed, the first is the \n'          )
		fl.write( '#      perpendicular thermal speed and second is\n' )
		fl.write( '#      the parallel.\n'                             )
		fl.write( '#   -- A quantity with an uncertainty value has\n'  )
		fl.write( '#      that value written immediately below it.\n'  )
		fl.write( '#      Uncertainty values are absolute (versus\n'   )
		fl.write( '#      relative) uncertainties and are scaled so\n' )
		fl.write( '#      that the reduced chi-squared returned by\n'  )
		fl.write( '#      the non-linear fit is unity.\n'              )
		fl.write( '#   -- The units on numerical quantities are as\n'  )
		fl.write( '#      follows:\n'                                  )
		fl.write( '#        -- Magnetic field: nT\n'            )
		fl.write( '#        -- Mass:           proton mass\n'   )
		fl.write( '#        -- Charge:         proton charge\n' )
		fl.write( '#        -- Density:        cm^-3\n'         )
		fl.write( '#        -- Velocity:       km/s\n'          )
		fl.write( txt_sep )

		# Write the values of the parameters for each spectum.

		for plas in self.series.arr :

			# Write the timestamp.

			fl.write( '\n' )
			fl.write( 'Timestamp:  ' )
			fl.write( calc_time_sec( plas['time'] ) )

			# Write the magnetic field.

			fl.write( '\n' )
			fl.write( 'B-Field:   ' )
			fl.write( txt_num.format( plas['b0_x'] ) )
			fl.write( txt_num.format( plas['b0_y'] ) )
			fl.write( txt_num.format( plas['b0_z'] ) )

			# Write the bulk velocity and it's uncertainty.

			fl.write( '\n' )
			fl.write( 'Velocity:  ' )
			fl.write( txt_num.format( plas['v0_x'] ) )
			fl.write( txt_num.format( plas['v0_y'] ) )
			fl.write( txt_num.format( plas['v0_z'] ) )
			fl.write( '\n' )
			fl.write( txt_spc )
			fl.write( txt_num.format( plas['sig_v0_x'] ) )
			fl.write( txt_num.format( plas['sig_v0_y'] ) )
			fl.write( txt_num.format( plas['sig_v0_z'] ) )

			# Write the values for each species.

			for spec in plas.arr_spec :

				# Write the values for the general parameters of
				# the species.

				fl.write( '\n' )
				fl.write( 'Species:    ' )
				fl.write( spec['name'] )
				fl.write( ' (' )
				fl.write( spec['sym'] )
				fl.write( ')' )

				fl.write( '\n' )
				fl.write( txt_spc )
				fl.write( txt_num.format( spec['m'] ) )
				fl.write( ' ' )
				fl.write( txt_num.format( spec['q'] ) )

				# Write the values for the parameters of each
				# population of the species.

				for pop in plas.lst_pop( spec ) :

					# Write the population name.

					fl.write( '\n' )
					fl.write( txt_spc )
					fl.write( ' ' )
					fl.write( 'Population: ' )
					fl.write( pop['name'] )
					fl.write( ' (' )
					fl.write( pop['sym'] )
					fl.write( ')' )

					# Write the population's density (and
					# uncertainty therin).

					fl.write( '\n' )
					fl.write( txt_spc )
					fl.write( txt_spc )
					fl.write( '  ' )
					fl.write( 'Density:   ' )
					fl.write( txt_num.format( pop['n'] ) )
					fl.write( '\n' )
					fl.write( txt_spc )
					fl.write( txt_spc )
					fl.write( txt_spc )
					fl.write( '  ' )
					fl.write( txt_num.format( pop['sig_n'] ) )

					# If applicable, write the populations's
					# drift (and uncertainty therin).

					if ( pop.drift ):
						fl.write( '\n' )
						fl.write( txt_spc )
						fl.write( txt_spc )
						fl.write( '  ' )
						fl.write( 'Drift vel: ' )
						fl.write( txt_num.format(
						                   pop['dv'] ) )
						fl.write( '\n' )
						fl.write( txt_spc )
						fl.write( txt_spc )
						fl.write( txt_spc )
						fl.write( '  ' )
						fl.write( txt_num.format(
						                 pop['sig_dv'] ) )

					# Write the population's thermal
					# speed(s) (and uncertainty therin).

					fl.write( '\n' )
					fl.write( txt_spc )
					fl.write( txt_spc )
					fl.write( '  ' )
					fl.write( 'Thrm Speed:' )
					if ( pop.aniso ) :
						fl.write( txt_num.format(
						                pop['w_per'] ) )
						fl.write( txt_num.format(
						                pop['w_par'] ) )
					else :
						fl.write( txt_num.format(
						                    pop['w'] ) )
					fl.write( '\n' )
					fl.write( txt_spc )
					fl.write( txt_spc )
					fl.write( txt_spc )
					fl.write( '  ' )
					if ( pop.aniso ) :
						fl.write( txt_num.format(
						              pop['sig_w_per'] ) )
						fl.write( txt_num.format(
						              pop['sig_w_par'] ) )
					else :
						fl.write( txt_num.format(
						                  pop['sig_w'] ) )

			# Write a seperator.

			fl.write( '\n' )
			fl.write( txt_sep )

		# Close the output file.

		fl.close( )

		# Message the user that the export was successful.

		self.emit( SIGNAL('janus_mesg'), 'core', 'end', 'xprt' )

		# If requested, exit the application.

		if ( exit ) :
			self.emit( SIGNAL('janus_exit') )
