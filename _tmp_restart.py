import os, subprocess, time
os.system("cp /opt/jockey/backend/backend/router.py /opt/jockey/backend/router.py")
os.system("find /opt/jockey/backend -name __pycache__ -exec rm -rf {} + 2>/dev/null")
os.system("kill -9 $(pgrep -f 'uvicorn main:app') 2>/dev/null")
time.sleep(2)
subprocess.run(["systemctl", "start", "jockey-backend"], check=True)
print("Done")
