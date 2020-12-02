from mdsuite.experiment.experiment_flux import ProjectFlux

if __name__ == '__main__':
    argon = ProjectFlux(analysis_name="Argon_70",
                        new_project=True,
                        storage_path=".",
                        temperature=70.0,
                        time_step=4,
                        filename="../trajectory_files/flux.dat",
                        units='real')

    argon.green_kubo_thermal_conductivity(data_range=800, plot=False)