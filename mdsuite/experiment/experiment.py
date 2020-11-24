"""
Authors: Samuel Tovey, Francisco Torres
Affiliation: Institute for Computational Physics, University of Stuttgart ; 
Contact: stovey@icp.uni-stuttgart.de ; tovey.samuel@gmail.com
Purpose: Class functionality of the program
"""

import os
import sys

import h5py as hf
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit
from tqdm import tqdm
import warnings
from pathlib import Path

import mdsuite.utils.constants as constants
import mdsuite.utils.meta_functions as meta_functions
import mdsuite.experiment.experiment_methods as methods

# File readers
from mdsuite.file_io.lammps_trajectory_files import LAMMPSTrajectoryFile

# Analysis modules
from mdsuite.analysis import einstein_diffusion_coefficients
from mdsuite.analysis import green_kubo_diffusion_coefficients
from mdsuite.analysis import green_kubo_ionic_conductivity
from mdsuite.analysis import einstein_helfand_ionic_conductivity
from mdsuite.analysis import radial_distribution_function

# Transformation modules
from mdsuite.transformations import unwrap_coordinates

plt.style.use('bmh')
tqdm.monitor_interval = 0
warnings.filterwarnings("ignore")


class Experiment(methods.ProjectMethods):
    """ Experiment from simulation

    Attributes:

        trajectory_file (str) -- trajectory_file of the trajectory

        analysis_name (str) -- name of the analysis being performed e.g. NaCl_1400K

        storage_path (str) -- where to store the data (best to have  drive capable of storing large files)

        temperature (float) -- temperature of the system

        time_step (float) -- time step in the simulation e.g 0.002

        volume (float) -- volume of the system

        species (dict) -- dictionary of the species in the system and their indices in the trajectory. e.g.
                          {'Na': [1, 3, 7, 9], 'Cl': [0, 2, 4, 5, 6, 8]}

        number_of_atoms (int) -- number of atoms in the system

        properties (dict) -- properties in the trajectory available for analysis, not important for understanding

        property_groups (list) -- property groups, e.g ["Forces", "Positions", "Velocities", "Torques"]

        dimensions (float) -- dimensionality of the system e.g. 3.0

        box_array (list) -- box lengths, e.g [10.7, 10.7, 10.8]

        number_of_configurations (int) -- number of configurations in the trajectory

        time_dimensions (list) -- Time domain in the system, e.g, for a 1ns simulation, [0.0, 1e-9]

        diffusion_coefficients (dict) -- Dictionary of diffusion coefficients including from Einstein and Green-Kubo,
                                         and split again into singular and distinct coefficients.
        ionic_conductivity (dict) -- Ionic conductivity of the system e.g. 4.5 S/cm
        thermal_conductivity (dict) -- The thermal conductivity of the material. Can be calculated as a global or local
                                       calculation and is therefore labelled as such.
    """

    def __init__(self, analysis_name, storage_path='./', timestep=1.0, temperature=0, units='real'):
        """ Initialise with trajectory_file """

        self.trajectory_file = None  # will be set later
        self.analysis_name = analysis_name
        self.storage_path = storage_path
        self.temperature = temperature
        self.time_step = timestep
        self.sample_rate = None
        self.batch_size = None
        self.volume = None
        self.species = None
        self.number_of_atoms = None
        self.properties = None
        self.property_groups = None
        self.dimensions = None
        self.box_array = None
        self.number_of_configurations = 0
        self.time_dimensions = None
        self.units = self.units_to_si(units)
        self.diffusion_coefficients = {"Einstein": {"Singular": {}, "Distinct": {}},
                                       "Green-Kubo": {"Singular": {}, "Distinct": {}}}
        self.ionic_conductivity = {"Einstein-Helfand": {},
                                   "Green-Kubo": {},
                                   "Nernst-Einstein": {"Einstein": None, "Green-Kubo": None},
                                   "Corrected Nernst-Einstein": {"Einstein": None, "Green-Kubo": None}}
        self.thermal_conductivity = {'Global': {"Green-Kubo": {}}}

        test_dir = Path(f"{self.storage_path}/{self.analysis_name}")
        if test_dir.exists():
            print("This model already exists, loading it now.")
            self._load_class()
        else:
            print("Building a new model.")
            self.build_model()

    def _process_input_file(self):
        """ Process the input file

        A trivial function to get the format of the input file. Will probably become more useful when we add support
        for more file formats.
        """

        if self.trajectory_file[-6:] == 'extxyz':
            file_format = 'extxyz'
        else:
            file_format = 'lammps_traj'

        return file_format

    def get_system_properties(self):
        """ Get the properties of the system

        This method will call the Get_X_Properties depending on the file format. This function will update all of the
        class attributes and is necessary for the operation of the Build database method.

        args:
            file_format (str) -- Format of the file being read
        """

        file_format = self._process_input_file()  # Collect file format information
        trajectory_reader = self._select_file_reader(file_format)

        return trajectory_reader

    def _select_file_reader(self, argument):
        """ Switcher function to select relevant file reader """

        switcher = {
            'lammps_traj': LAMMPSTrajectoryFile
        }

        choice = switcher.get(argument, lambda: "Invalid filetype")

        return choice(self)

    def build_model(self):
        """ Build the 'experiment' for the analysis

        A method to build the database in the hdf5 format. Within this method, several other are called to develop the
        database skeleton, get configurations, and process and store the configurations. The method is accompanied
        by a loading bar which should be customized to make it more interesting.
        """

        # Create new analysis directory and change into it
        try:
            os.mkdir(f'{self.storage_path}/{self.analysis_name}')
        except FileExistsError:
            pass


        self._save_class()

        print(f"** Experiment has been constructed for {self.analysis_name} **")

    def _get_minimal_class_state(self):
        """ Get a minimum umber of class properties for comparison """

        return [self.number_of_atoms, list(self.species), self.box_array]

    def _update_database(self):
        """ Update a pre-existing database """

        trajectory_reader = self.get_system_properties()  # select the correct trajectory reader
        # get properties of new trajectory
        compare_data = trajectory_reader.process_trajectory_file(update_class=False)
        class_state = self._get_minimal_class_state()

        if compare_data[:-1] == class_state:
            self.number_of_configurations += compare_data[3]

            trajectory_reader.resize_database()  # resize the database to accommodate the new data

            self._fill_database(trajectory_reader, counter=int(self.number_of_configurations - compare_data[3]))
        else:
            print(compare_data[:-1] == class_state)

    def _fill_database(self, trajectory_reader, counter=0):
        """ Loads data into a hdf5 database """

        loop_range = int((self.number_of_configurations - counter) / self.batch_size)
        with hf.File("{0}/{1}/{1}.hdf5".format(self.storage_path, self.analysis_name), "r+") as database:
            with open(self.trajectory_file) as f:
                for _ in tqdm(range(loop_range), ncols=10):
                    batch_data = trajectory_reader.read_configurations(self.batch_size, f)

                    trajectory_reader.process_configurations(batch_data, database, counter)

                    counter += self.batch_size

    def _build_new_database(self):
        """ Build a new database """

        trajectory_reader = self.get_system_properties()  # select the correct trajectory reader
        trajectory_reader.process_trajectory_file()  # get properties of the trajectory and update the class
        trajectory_reader.build_database_skeleton()  # Build the database skeleton

        self._fill_database(trajectory_reader)

        self.build_species_dictionary()  # Beef up the species dictionary
        self._save_class()

    def add_data(self, trajectory_file=None):
        """ Add data to the database """

        if trajectory_file is None:
            print("No data has been given")
            sys.exit()

        self.trajectory_file = trajectory_file  # Update the current class trajectory file

        # Check to see if a database exists
        test_db = Path(f"{self.storage_path}/{self.analysis_name}/{self.analysis_name}.hdf5")
        if test_db.exists():
            self._update_database()
        else:
            self._build_new_database()

        self._save_class()

    def unwrap_coordinates(self, species=None, center_box=True):
        """ unwrap coordinates of trajectory

        For a number of properties the input data must in the form of unwrapped coordinates. This function takes the
        stored trajectory and returns the unwrapped coordinates so that they may be used for analysis.
        """

        transformation_ufb = unwrap_coordinates.CoordinateUnwrapper(self, species, center_box)  # load the unwrapper
        transformation_ufb.unwrap_particles()  # unwrap the coordinates

    def load_matrix(self, identifier, species=None):
        """ Load a desired property matrix

        args:
            identifier (str) -- Name of the matrix to be loaded, e.g. Unwrapped_Positions, Velocities
            species (list) -- List of species to be loaded

        returns:
            Matrix of the property
        """

        if species is None:
            species = list(self.species.keys())
        property_matrix = []  # Define an empty list for the properties to fill

        with hf.File(f"{self.storage_path}/{self.analysis_name}/{self.analysis_name}.hdf5", "r+") as database:
            for item in list(species):
                # Unwrap the positions if they need to be unwrapped
                if identifier == "Unwrapped_Positions" and "Unwrapped_Positions" not in database[item]:
                    print("We first have to unwrap the coordinates... Doing this now")
                    self.unwrap_coordinates(species=[item])
                if identifier not in database[item]:
                    print("This data was not found in the database. Was it included in your simulation input?")
                    return

                property_matrix.append(np.dstack((database[item][identifier]['x'],
                                                  database[item][identifier]['y'],
                                                  database[item][identifier]['z'])))

        if len(property_matrix) == 1:
            return property_matrix[0]
        else:
            return property_matrix

    def einstein_diffusion_coefficients(self, plot=False, singular=True, distinct=False, species=None, data_range=500):
        """ Calculate the Einstein self diffusion coefficients

            A function to implement the Einstein method for the calculation of the self diffusion coefficients
            of a liquid. In this method, unwrapped trajectories are read in and the MSD of the positions calculated and
            a gradient w.r.t time is calculated over several ranges to calculate an error measure.

            args:
                plot (bool = False) -- If True, a plot of the msd will be displayed
                Singular (bool = True) -- If True, will calculate the singular diffusion coefficients
                Distinct (bool = False) -- If True, will calculate the distinct diffusion coefficients
                species (list) -- List of species to analyze
                data_range (int) -- Range over which the values should be calculated
        """

        if species is None:
            species = list(self.species.keys())

        calculation_ed = einstein_diffusion_coefficients._EinsteinDiffusionCoefficients(self, plot=plot,
                                                                                        singular=singular,
                                                                                        distinct=distinct,
                                                                                        species=species,
                                                                                        data_range=data_range)

        calculation_ed._single_diffusion_coefficients()

        self._save_class()  # Update class state

    def green_kubo_diffusion_coefficients(self, data_range=500, plot=False, singular=True, distinct=False, species=None):
        """ Calculate the Green_Kubo Diffusion coefficients

        Function to implement a Green-Kubo method for the calculation of diffusion coefficients whereby the velocity
        autocorrelation function is integrated over and divided by 3. Autocorrelation is performed using the scipy
        fft correlate function in order to speed up the calculation.
        """

        # Load all the species if none are specified
        if species is None:
            species = list(self.species.keys())

        calculation_gkd = green_kubo_diffusion_coefficients._GreenKuboDiffusionCoefficients(self, plot=plot,
                                                                                            singular=singular,
                                                                                            distinct=distinct,
                                                                                            species=species,
                                                                                            data_range=data_range)

        if singular:
            calculation_gkd._singular_diffusion_coefficients()
        if distinct:
            calculation_gkd._distinct_diffusion_coefficients()

        self._save_class()  # Update class state

    def nernst_einstein_conductivity(self):
        """ Calculate Nernst-Einstein Conductivity

        A function to determine the Nernst-Einstein (NE) as well as the corrected Nernst-Einstein (CNE)
        conductivity of a system.

        """
        truth_array = [[bool(self.diffusion_coefficients["Einstein"]["Singular"]),
                        bool(self.diffusion_coefficients["Einstein"]["Distinct"])],
                       [bool(self.diffusion_coefficients["Green-Kubo"]["Singular"]),
                        bool(self.diffusion_coefficients["Green-Kubo"]["Distinct"])]]

        def _ne_conductivity(_diffusion_coefficients):
            """ Calculate the standard Nernst-Einstein Conductivity for the system

            args:
                _diffusion_coefficients (dict) -- dictionary of diffusion coefficients
            """

            numerator = self.number_of_atoms * (constants.elementary_charge ** 2)
            denominator = constants.boltzmann_constant * self.temperature * (self.volume * (self.length_unit ** 3))
            prefactor = numerator / denominator

            diffusion_array = []
            for element in self.species:
                diffusion_array.append(_diffusion_coefficients["Singular"][element] *
                                       abs(self.species[element]['charge'][0]) *
                                       (len(self.species[element]['indices']) / self.number_of_atoms))

            return (prefactor * np.sum(diffusion_array)) / 100

        def _cne_conductivity(_singular_diffusion_coefficients, _distinct_diffusion_coefficients):
            print("Sorry, this currently isn't available")
            return

            numerator = self.number_of_atoms * (constants.elementary_charge ** 2)
            denominator = constants.boltzmann_constant * self.temperature * (self.volume * (self.length_unit ** 3))
            prefactor = numerator / denominator

            singular_diffusion_array = []
            for element in self.species:
                singular_diffusion_array.append(_singular_diffusion_coefficients[element] *
                                                (len(self.species[element]['indices']) / self.number_of_atoms))

        if all(truth_array[0]) is True and all(truth_array[1]) is True:
            "Update all NE and CNE cond"
            pass

        elif not any(truth_array[0]) is True and not any(truth_array[1]) is True:
            "Run the diffusion analysis and then calc. all"
            pass

        elif all(truth_array[0]) is True and not any(truth_array[1]) is True:
            """ Calc NE, CNE for Einstein """
            pass

        elif all(truth_array[1]) is True and not any(truth_array[0]) is True:
            """ Calc all NE, CNE for GK """
            pass

        elif truth_array[0][0] is True and truth_array[1][0] is True:
            """ Calc just NE for EIN and GK """

            self.ionic_conductivity["Nernst-Einstein"]["Einstein"] = _ne_conductivity(
                self.diffusion_coefficients["Einstein"])
            self.ionic_conductivity["Nernst-Einstein"]["Green-Kubo"] = _ne_conductivity(
                self.diffusion_coefficients["Green-Kubo"])

            print(f'Nernst-Einstein Conductivity from Einstein Diffusion: '
                  f'{self.ionic_conductivity["Nernst-Einstein"]["Einstein"]} S/cm\n'
                  f'Nernst-Einstein Conductivity from Green-Kubo Diffusion: '
                  f'{self.ionic_conductivity["Nernst-Einstein"]["Green-Kubo"]} S/cm')

        elif truth_array[0][0] is True and not any(truth_array[1]) is True:
            """ Calc just NE for EIN """

            self.ionic_conductivity["Nernst-Einstein"]["Einstein"] = _ne_conductivity(
                self.diffusion_coefficients["Einstein"])
            print(f'Nernst-Einstein Conductivity from Einstein Diffusion: '
                  f'{self.ionic_conductivity["Nernst-Einstein"]["Einstein"]} S/cm')

        elif truth_array[1][0] is True and not any(truth_array[0]) is True:
            """ Calc just NE for GK """

            self.ionic_conductivity["Nernst-Einstein"]["Green-Kubo"] = _ne_conductivity(
                self.diffusion_coefficients["Green-Kubo"])
            print(f'Nernst-Einstein Conductivity from Green-Kubo Diffusion: '
                  f'{self.ionic_conductivity["Nernst-Einstein"]["Green-Kubo"]} S/cm')

        elif all(truth_array[0]) is True and truth_array[1][0] is True:
            """ Calc CNE for EIN and just NE for GK"""
            pass

        elif all(truth_array[1]) is True and truth_array[0][0] is True:
            """ Calc CNE for GK and just NE for EIN"""
            pass

        else:
            print("This really should not be possible... something has gone horrifically wrong")
            return

        self._save_class()  # Update class state

    def einstein_helfand_ionic_conductivity(self, data_range, plot=False):
        """ Calculate the Einstein-Helfand Ionic Conductivity

        A function to use the mean square displacement of the dipole moment of a system to extract the
        ionic conductivity

        args:
            data_range (int) -- time range over which the measurement should be performed
        kwargs:
            plot(bool=False) -- If True, will plot the MSD over time
        """

        calculation_ehic = einstein_helfand_ionic_conductivity._EinsteinHelfandIonicConductivity(self, data_range, plot)
        calculation_ehic._calculate_ionic_conductivity()
        self._save_class

    def green_kubo_ionic_conductivity(self, data_range, plot=False):
        """ Calculate Green-Kubo Ionic Conductivity

        A function to use the current autocorrelation function to calculate the Green-Kubo ionic conductivity of the
        system being studied.

        args:
            data_range (int) -- number of data points with which to calculate the conductivity

        kwargs:
            plot (bool=False) -- If True, a plot of the current autocorrelation function will be generated

        returns:
            sigma (float) -- The ionic conductivity in units of S/cm

        """

        calculation_gkic = green_kubo_ionic_conductivity._GreenKuboIonicConductivity(self, plot=plot,
                                                                                     data_range=data_range)
        calculation_gkic._calculate_ionic_conductivity()

        self._save_class()  # Update class state

    # TODO def green_kubo_viscosity(self):

    def radial_distribution_function(self, plot=True, bins=500, cutoff=None):
        """ Calculate the radial distribution function """

        calculation_rdf = radial_distribution_function.RadialDistributionFunction(self, plot=plot,
                                                                                  bins=bins,
                                                                                  cutoff=cutoff)
        calculation_rdf.perform_analysis()  # run the analysis

    # TODO def kirkwood_buff_integrals(self):

    # TODO def structure_factor(self):

    # TODO def angular_distribution_function(self):