""" Calculate the Nernst-Einstein Conductivity of a experiment """

import numpy as np
import os
import yaml
import sys
import itertools
from typing import Union

from mdsuite.utils.units import boltzmann_constant, elementary_charge


class NernstEinsteinIonicConductivity:
    """
    Class for the calculation of the Nernst-Einstein ionic conductivity
    """

    def __init__(self, obj, corrected: bool = False):
        """
        Standard constructor

        Parameters
        ----------
        obj : Experiment
                Experiment class from which to read
        corrected : bool
                If true, the corrected Nernst Einstein will also be calculated
        """
        self.parent = obj                   # experiment class to call attributes from
        self.corrected = corrected          # if true, calculate the corrected Nernst-Einstein conductivity as well

        self.post_generation = True

        self.data = self._load_yaml_data()  # tensor_values to be read in
        self.truth_table = self._build_truth_table()  # build truth table for analysis

    def _load_yaml_data(self):
        """
        Load tensor_values from a yaml file

        Returns
        -------
        tensor_values: dict
                A dictionary of tensor_values stored in the yaml file
        """
        filepath = os.path.join(self.parent.database_path, "system_properties.yaml")  # collect the filepath
        f_object = open(filepath)
        loaded_data = yaml.load(f_object, Loader=yaml.FullLoader)  # load the tensor_values
        f_object.close()

        return loaded_data

    def _update_properties_file(self, analysis_name: str = None, data: list = None):
        """
        Update the experiment properties YAML file.
        """

        # Check if tensor_values has been given
        if data is None:
            print("No tensor_values provided")
            return

        with open(os.path.join(self.parent.database_path, 'system_properties.yaml')) as pfr:
            properties = yaml.load(pfr, Loader=yaml.Loader)  # collect the tensor_values in the yaml file

        with open(os.path.join(self.parent.database_path, 'system_properties.yaml'), 'w') as pfw:
            properties['ionic_conductivity'][analysis_name] = data
            yaml.dump(properties, pfw)

    def _build_truth_table(self):
        """
        Builds a truth table to communicate which tensor_values is available to the analysis.

        Returns
        -------
        truth_table : list
                A truth table communication which tensor_values is available for the analysis.
        """

        truth_table = [[[], []], [[], []]]
        method_strings = ['einstein_diffusion_coefficients', 'Green_Kubo_Diffusion']
        combinations = ['-'.join(tup) for tup in list(itertools.combinations_with_replacement(self.parent.species, 2))]

        row = 0
        for method in method_strings:
            temp_array = []
            for molecule in self.parent.species:
                temp_array.append(molecule in self.data['diffusion_coefficients'][method]['Singular'])
            truth_table[row][0] = all(temp_array)
            for combination in combinations:
                temp_array.append(combination in self.data['diffusion_coefficients'][method]['Distinct'])
            truth_table[row][1] = all(temp_array)

            row += 1

        return truth_table

    def _nernst_einstein(self, diffusion_information: dict):
        """
        Calculate the Nernst-Einstein ionic conductivity

        Parameters
        ----------
        diffusion_information : dict
                A dictionary of information about diffusion coefficients, e.g. {'Na': [1.3, 0.05], 'Cl: [1.8, 0.1]}
                where the second element of each list is the uncertainty of the first element.

        Returns
        -------
        Nernst-Einstein Ionic conductivity of the experiment in units of S/cm
        """

        # evaluate the prefactor
        numerator = self.parent.number_of_atoms * (elementary_charge ** 2)
        denominator = boltzmann_constant * self.parent.temperature * \
                      (self.parent.volume * (self.parent.units['length'] ** 3))
        prefactor = numerator / denominator

        diffusion_array = []
        for element in diffusion_information:
            charge_term = self.parent.species[element]['charge'][0] ** 2
            mass_fraction_term = len(self.parent.species[element]['indices']) / self.parent.number_of_atoms
            diffusion_array.append(float(diffusion_information[element][0]) * charge_term * mass_fraction_term)

        return prefactor * np.sum(diffusion_array)

    def _corrected_nernst_einstein(self, self_diffusion_information: dict, distinct_diffusion_information: dict):
        """
        Calculate the corrected Nernst-Einstein ionic conductivity

        Parameters
        ----------
        self_diffusion_information : dict
                dictionary containing information about self diffusion
        distinct_diffusion_information : dict
                dictionary containing information about distinct diffusion

        Returns
        -------
        Corrected Nernst-Einstein ionic conductivity in units of S/cm
        """

        # evaluate the prefactor
        numerator = self.parent.number_of_atoms * (elementary_charge ** 2)
        denominator = boltzmann_constant * self.parent.temperature * \
                      (self.parent.volume * (self.parent.units['length'] ** 3))
        prefactor = numerator / denominator

        diffusion_array = []
        for element in self_diffusion_information:
            charge_term = self.parent.species[element]['charge'][0]**2
            mass_fraction_term = len(self.parent.species[element]['indices']) / self.parent.number_of_atoms
            diffusion_array.append(float(self_diffusion_information[element][0]) * charge_term * mass_fraction_term)

        for couple in distinct_diffusion_information:
            constituents = couple.split('-')
            charge_term = self.parent.species[constituents[0]]['charge'][0] * \
                          self.parent.species[constituents[1]]['charge'][0]
            mass_fraction_term = (len(self.parent.species[constituents[0]]['indices']) / self.parent.number_of_atoms) * \
                                 (len(self.parent.species[constituents[1]]['indices']) / self.parent.number_of_atoms)
            diffusion_array.append(float(distinct_diffusion_information[couple][0]) * charge_term * mass_fraction_term)

        return prefactor * np.sum(diffusion_array)

    def _run_nernst_einstein(self):
        """
        Process truth table and run all possible nerst-einstein calculations

        Returns
        -------

        """
        ne_table = [self.truth_table[0][0], self.truth_table[1][0]]

        if ne_table[0]:
            data = self._nernst_einstein(self.data['diffusion_coefficients']['einstein_diffusion_coefficients']
                                         ['Singular'])
            self._update_properties_file(analysis_name='Nernst_Einstein_Einstein', data=str(data))
        if ne_table[1]:
            data = self._nernst_einstein(self.data['diffusion_coefficients']['Green_Kubo_Diffusion']['Singular'])
            self._update_properties_file(analysis_name='Nernst_Einstein_Green_Kubo', data=str(data))
        if not any(ne_table):
            print("There is no tensor_values to analyse, please run a diffusion calculation to proceed")
            sys.exit(1)

    def _run_corrected_nernst_einstein(self):
        """
        Process truth table and run all possible nernst-einstein calculations

        Returns
        -------
        Updates the experiment database_path
        """

        cne_table = [all(self.truth_table[0]), all(self.truth_table[1])]

        if cne_table[0]:
            data = self._corrected_nernst_einstein(self.data['diffusion_coefficients']
                                                   ['einstein_diffusion_coefficients']['Singular'],
                                                   self.data['diffusion_coefficients']
                                                   ['einstein_diffusion_coefficients']['Distinct'])
            self._update_properties_file(analysis_name='Corrected_Nernst_Einstein_Einstein', data=str(data))

        if cne_table[1]:
            data = self._corrected_nernst_einstein(self.data['diffusion_coefficients']['Green_Kubo_Diffusion']
                                                   ['Singular'],
                                                   self.data['diffusion_coefficients']['Green_Kubo_Diffusion']
                                                   ['Distinct'])
            self._update_properties_file(analysis_name='Corrected_Nernst_Einstein_Green_Kubo', data=str(data))

    def run_post_generation_analysis(self):
        """
        Run the analysis
        """

        self._run_nernst_einstein()
        if self.corrected:
            self._run_corrected_nernst_einstein()

    def _calculate_prefactor(self, species: Union[str, tuple] = None):
        """
        calculate the calculator pre-factor.

        Parameters
        ----------
        species : str
                Species property if required.
        Returns
        -------

        """
        raise NotImplementedError

    def _apply_operation(self, data, index):
        """
        Perform operation on an ensemble.

        Parameters
        ----------
        One tensor_values range of tensor_values to operate on.

        Returns
        -------

        """
        raise NotImplementedError

    def _apply_averaging_factor(self):
        """
        Apply an averaging factor to the tensor_values.
        Returns
        -------
        averaged copy of the tensor_values
        """
        raise NotImplementedError

    def _post_operation_processes(self, species: Union[str, tuple] = None):
        """
        call the post-op processes
        Returns
        -------

        """
        raise NotImplementedError

    def _update_output_signatures(self):
        """
        After having run _prepare managers, update the output signatures.

        Returns
        -------

        """
        raise NotImplementedError