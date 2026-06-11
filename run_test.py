import subprocess, sys
r = subprocess.run([sys.executable, sys.argv[1]], capture_output=True, text=True)
print("STDOUT:", r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout)
print("STDERR:", r.stderr[-2000:] if len(r.stderr) > 2000 else r.stderr)
print("EXIT:", r.returncode)
sys.exit(r.returncode)
