"""
This program and the accompanying materials are made available under the terms of the
Eclipse Public License v2.0 which accompanies this distribution, and is available at
https://www.eclipse.org/legal/epl-v20.html

SPDX-License-Identifier: EPL-2.0

Copyright Contributors to the MDSuite Project.
"""

"""
Exceptions for the mdsuite program
"""


class NoElementInDump(Exception):
    """
    Thrown when no elements are found in a dump file
    """
    pass


class NoTempInData(Exception):
    """
    Thrown when no temperature is found in a tensor_values file
    """
    pass


class NotApplicableToAnalysis(Exception):
    """
    Thrown when the function is not applicable to the type of analysis being performed
    """
    pass


class CannotPerformThisAnalysis(Exception):
    """
    Thrown when analysis cannot be reliably performed given the tensor_values
    """
    pass


class ElementMassAssignedZero(Exception):
    """
    Thrown when an element mass has been assigned zero.
    """
    pass


class NoGPUInSystem(Exception):
    """
    Thrown during experiment analysis when GPUs are being searched for.
    """

    def __init__(self):
        Exception.__init__(self, "No GPUs detected, continuing without GPU support")


class DatasetExists(Exception):
    """
    Thrown if a dataset in a hdf5 database_path already exists
    """
    pass


class RangeExceeded(Exception):
    """
    Thrown when the tensor_values range asked for exceeds the total number of configurations
    """
    pass


class DatabaseDoesNotExist(Exception):
    """
    Thrown when a preexisting database_path object is called but none exists
    """
    def __init__(self):
        """ Constructor method """
        self.message = "Database does not exists"
        super().__init__(self.message)


class NotInDataFile(Exception):
    """
    Thrown when a parameter is not in a data file.
    """
    pass
