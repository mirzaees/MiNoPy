### This is a manual for HPC users. It is based on job submission in [MinSAR](https://github.com/geodesymiami/rsmas_insar) app

In this workflow, you need to create jobs and then run them in order

To create jobs, run:
```
minopyApp.py $PWD/PichinchaSenDT142.template --dir minopy --jobfiles
```
After the jobs are created, you may run them with one of the appropriate submit commands:
```
submit_jobs.bash $PWD/PichinchaSenDT142.template --minopy
(submit_jobs.bash $PWD/PichinchaSenDT142.template --dostep minopy)
```
This uses the `sbatch_conditional.bash` commmand, that can be used for individual run_files:

```
sbatch_conditional.bash minopy/run_files/run_01_minopy_load_slc 
sbatch_conditional.bash minopy/run_files/run_02_minopy_inversion
sbatch_conditional.bash minopy/run_files/run_03_minopy_ifgram
sbatch_conditional.bash minopy/run_files/run_04_minopy_unwrap
sbatch_conditional.bash minopy/run_files/run_05_minopy_load_ifgram
sbatch_conditional.bash minopy/run_files/run_06_mintpy_correct_unwrap_error 
sbatch_conditional.bash minopy/run_files/run_07_minopy_phase_to_range
sbatch_conditional.bash minopy/run_files/run_08_mintpy_corrections
```
