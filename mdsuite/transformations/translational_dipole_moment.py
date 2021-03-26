"""
Python module to calculate the translational dipole in a experiment.
"""

import numpy as np
from tqdm import tqdm
import os
import tensorflow as tf

from mdsuite.transformations.transformations import Transformations
from mdsuite.database.database import Database
from mdsuite.utils.meta_functions import join_path
from mdsuite.memory_management.memory_manager import MemoryManager
from mdsuite.database.data_manager import DataManager


class TranslationalDipoleMoment(Transformations):
    """
    Class to generate and store the ionic current of a experiment

    Attributes
    ----------
    experiment : object
            Experiment this transformation is attached to.
    """

    def __init__(self, experiment: object):
        """
        Constructor for the Ionic current calculator.

        Parameters
        ----------
        experiment : object
                Experiment this transformation is attached to.
        """
        super().__init__()
        self.experiment = experiment
        self.batch_size: int
        self.n_batches: int
        self.remainder: int

        self.database = Database(name=os.path.join(self.experiment.database_path, "database.hdf5"),
                                 architecture='simulation')

    def _prepare_monitors(self, data_path: list):
        """
        Prepare the tensor_values and memory managers.

        Parameters
        ----------
        data_path : list
                List of tensor_values paths to load from the hdf5 database_path.

        Returns
        -------

        """
        self.memory_manager = MemoryManager(data_path=data_path, database=self.database, scaling_factor=5,
                                            memory_fraction=0.5)
        self.data_manager = DataManager(data_path=data_path, database=self.database)
        self.batch_size, self.n_batches, self.remainder = self.memory_manager.get_batch_size()
        self.data_manager.batch_size = self.batch_size
        self.data_manager.n_batches = self.n_batches
        self.data_manager.remainder = self.remainder

    def _transformation(self, data: tf.Tensor):
        """
        Calculate the translational dipole moment of the system.

        Returns
        -------

        """
        dipole_moment = tf.reduce_sum(data, axis=1)  # Convert the results to a tf.tensor

        # Build the charge tensor for assignment
        system_charges = [self.experiment.species[atom]['charge'][0] for atom in
                          self.experiment.species]  # load species charge
        charge_tuple = []  # define empty array for the charges
        for charge in system_charges:  # loop over each species charge
            # Build a tensor of charges allowing for memory management.
            charge_tuple.append(tf.ones([self.batch_size, 3], dtype=tf.float64) * charge)

        charge_tensor = tf.stack(charge_tuple)  # stack the tensors into a single object
        dipole_moment = tf.reduce_sum(dipole_moment*charge_tensor, axis=0)  # Calculate the final dipole moments

        return dipole_moment

    def _prepare_database_entry(self):
        """
        Add the relevant tensor_values sets and groups in the database_path

        Parameters
        ----------
        species : str
                Species for which tensor_values will be added.
        Returns
        -------
        tensor_values structure for use in saving the tensor_values to the database_path.
        """

        path = join_path('Translational_Dipole_Moment', 'Translational_Dipole_Moment')  # name of the new database_path
        dataset_structure = {path: (self.experiment.number_of_configurations, 3)}
        self.database.add_dataset(dataset_structure)  # add a new dataset to the database_path
        data_structure = {path: {'indices': np.s_[:], 'columns': [0, 1, 2]}}

        return data_structure

    def _compute_dipole_moment(self):
        """
        Loop over batches and compute the dipole moment
        Returns
        -------

        """
        data_structure = self._prepare_database_entry()
        data_path = [join_path(species, 'Unwrapped_Positions') for species in self.experiment.species]
        self._prepare_monitors(data_path)
        batch_generator, batch_generator_args = self.data_manager.batch_generator()
        data_set = tf.data.Dataset.from_generator(batch_generator,
                                                  args=batch_generator_args,
                                                  output_signature=tf.TensorSpec(shape=(len(data_path),
                                                                                        None,
                                                                                        self.batch_size,
                                                                                        3), dtype=tf.float64))
        data_set.prefetch(tf.data.experimental.AUTOTUNE)
        for index, x in enumerate(data_set):
            data = self._transformation(x)
            self._save_coordinates(data, index, self.batch_size, data_structure)

    def _save_coordinates(self, data: tf.Tensor, index: int, batch_size: int, data_structure: dict):
        """
        Save the tensor_values into the database_path

        Parameters
        ----------
        species : str
                name of species to update in the database_path.
        Returns
        -------
        saves the tensor_values to the database_path.
        """
        self.database.add_data(data=data,
                               structure=data_structure,
                               start_index=index,
                               batch_size=batch_size,
                               system_tensor=True)

    def run_transformation(self):
        """
        Run the ionic current transformation
        Returns
        -------

        """
        self._compute_dipole_moment()  # run the transformation.
        self.experiment.memory_requirements = self.database.get_memory_information()