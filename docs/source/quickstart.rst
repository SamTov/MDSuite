Quickstart Guide
================

Installation
------------

With pip:

.. code-block:: console

    $ cd MDSuite
    $ pip install . --user

Usage
-----

As MDSuite is installed simply as a python package, once installed, it can be called from any 
python program you are writing. This is done in the usual way, 

.. code-block:: python
        
        import mdsuite
        import mdsuite as mds
        from mdsuite import ...

which will load whichever modules are desired. Once you have import the module, you will need 
to begin your first analysis. This can be done as follows.

.. code-block:: python
        
        import mdsuite as mds

        test_project = mds.Experiment(analysis_name="this_is_a_test",
                                      new_project=True,
                                      storage_path="/path/for/database/storage/",
                                      temperature=temperature_of_simulation,
                                      time_step=simulation_time_step,
                                      time_unit=time_unit_for_SI_conversion,
                                      length_unit=length_unit_for_SI_conversion,
                                      filename="/path/to/trajectory/data")

Once this has been constructed, and the database has been built, you will have access to all of 
the methods currently available in the mdsuite package. For information about what these are, go 
and check out the examples directory and run some for yourself.