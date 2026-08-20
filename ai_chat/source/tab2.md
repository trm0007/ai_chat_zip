
now get the model.py file from user output directory and run it if user say proceed or yes or run it. ask user before run it. ask user should i run ur model.py file or wil u upload ur corrected model.py file?

 using import subprocess, sys

def run_test_py(test_file):
    result = subprocess.run([sys.executable, test_file], capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode.

2. before running analysis check the node numbers. if the total node numbers more than 1500 then ask user to reduce total node numbers below 1500.

3. then save raw .ODB file into user output directory


