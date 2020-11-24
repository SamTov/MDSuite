"""
Class for the calculation of the Green-Kubo ionic conductivity.

Author: Samuel Tovey

Description: This module contains the code for the Green-Kubo ionic conductivity class. This class is called by the
Experiment class and instantiated when the user calls the Experiment.green_kubo_ionic_conductivity method.
The methods in class can then be called by the Experiment.green_kubo_ionic_conductivity method and all necessary
calculations performed.
"""

# Python standard packages
import matplotlib.pyplot as plt
from scipy import signal
import numpy as np
import warnings

# Import user packages
from tqdm import tqdm

# Import MDSuite modules
import mdsuite.utils.constants as constants

# Set style preferences, turn off warning, and suppress the duplication of loading bars.
plt.style.use('bmh')
tqdm.monitor_interval = 0
warnings.filterwarnings("ignore")


class _GreenKuboIonicConductivity:
    """ Class for the Green-Kubo ionic conductivity implementation

    additional attrbs:
        plot
        singular
        distinct
        species
        data_range
    """

    def __init__(self, obj, plot=False, data_range=500):
        self.parent = obj
        self.plot = plot
        self.data_range = int(data_range)
        self.number_of_configurations = self.parent.number_of_configurations - self.parent.number_of_configurations % \
                                        self.parent.batch_size
        self.time = np.linspace(0.0, data_range * self.parent.time_step * self.parent.sample_rate, data_range)
        self.loop_range = self.number_of_configurations - data_range - 1
        self.correlation_time = 1

    def _calculate_system_current(self):
        """ Calculate the ionic current of the system

        :return: system_current (numpy array) -- ionic current of the system as a vector of shape (n_confs, 3)
        """

        velocity_matrix = self.parent.load_matrix("Velocities")  # Load the velocity matrix
        species_charges = [self.parent.species[atom]['charge'][0] for atom in self.parent.species]

        system_current = np.zeros((self.number_of_configurations, 3))  # instantiate the current array
        # Calculate the total system current
        for i in range(len(velocity_matrix)):
            system_current += np.array(np.sum(velocity_matrix[i][:, 0:], axis=0)) * species_charges[i]

        return system_current

    def _calculate_ionic_conductivity(self):
        """ Calculate the ionic conductivity in the system """

        system_current = self._calculate_system_current()  # get the ionic current

        # Calculate the prefactor
        numerator = (constants.elementary_charge ** 2) * (self.parent.units['length'] ** 2)
        denominator = 3 * constants.boltzmann_constant * self.parent.temperature * self.parent.volume * \
                      (self.parent.length_unit ** 3) * self.data_range * self.parent.units['time']
        prefactor = numerator / denominator

        sigma = []
        parsed_autocorrelation = np.zeros(self.data_range)  # Define the parsed array
        for i in tqdm(range(0, self.loop_range, self.correlation_time), ncols=10):
            jacf = np.zeros(2 * self.data_range - 1)  # Define the empty jacf array
            # Calculate the current autocorrelation
            jacf += (signal.correlate(system_current[:, 0][i:i + self.data_range],
                                      system_current[:, 0][i:i + self.data_range],
                                      mode='full', method='fft') +
                     signal.correlate(system_current[:, 1][i:i + self.data_range],
                                      system_current[:, 1][i:i + self.data_range],
                                      mode='full', method='fft') +
                     signal.correlate(system_current[:, 2][i:i + self.data_range],
                                      system_current[:, 2][i:i + self.data_range],
                                      mode='full', method='fft'))

            jacf = jacf[int((len(jacf) / 2)):]  # Cut the negative part of the current autocorrelation
            parsed_autocorrelation += jacf
            sigma.append(prefactor*np.trapz(jacf, x=self.time))  # Update the conductivity array

        self.parent.ionic_conductivity["Green-Kubo"] = np.mean(sigma)/100

        parsed_autocorrelation /= max(parsed_autocorrelation)  # Get the normalized autocorrelation plot data
        plt.plot(self.time, parsed_autocorrelation)
        plt.xlabel("Time (ps)")
        plt.ylabel("Normalize JACF")
        #plt.savefig(f"{self.parent.cwd}/Images/Green_Kubo_Ionic_Conductivity.eps", format='eps')
        if self.plot:
            plt.show()




