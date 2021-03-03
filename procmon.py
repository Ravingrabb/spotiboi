import psutil
import time
# Iterate over all running process

while True: #Infinite loop
    # закрытие мусорных процессов
    for proc in psutil.process_iter():
        try:
            # Get process name & pid from process object.
            processName = proc.name()
            processID = proc.pid
            if processName == 'www-browser':
                print(processName , ' ::: ', processID, ' will be killed')
                try:
                    proc.kill()
                except:
                    print('not killed, lol')
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    time.sleep(3600) #Wait 600s (10 min) before re-entering the cycle


