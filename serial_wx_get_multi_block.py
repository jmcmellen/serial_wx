import serial
from multiprocessing import Process, Pipe, Manager
import time
import random
import speech
import requests
import xml.etree.ElementTree as ET
from httpcache import CachingHTTPAdapter

def serial_stuff(target_temp, signal, p):
    com = serial.serial_for_url("COM10", timeout=2)
    line_buffer = ""
    output_temp = target_temp.value
    while True:
        try:
            #print "Reading serial"
            byte = com.read(1)
            if signal.value > 0:
                raise Exception
            if byte == '\r':
                #print line_buffer #Or pass the data somewhere else
                if output_temp < -998:
                    foo = com.write("E000\r\n")
                elif output_temp < 0:
                    foo = com.write("{0}\r\n".format(output_temp))
                else:
                    foo = com.write("+{0}\r\n".format(output_temp))
                if output_temp < -998 and target_temp >= -998:
                    output_temp = target_temp.value
                elif output_temp < target_temp.value:
                    output_temp = output_temp + 1
                elif output_temp > target_temp.value:
                    output_temp = output_temp - 1
                else:
                    pass
                line_buffer = ''
            else:
                #print byte
                line_buffer = line_buffer + byte
        except:
            com.close()
            break
    print "Serial process finishing"

def web_stuff(target_temp, signal, p, history):
    run_counter = 0
    location_url = "http://www.weather.gov/data/current_obs/KSGF.xml"
    s = requests.Session()
    s.mount('http://', CachingHTTPAdapter())
    last_obs_time = ''

    while True:
        try:
            req = s.get(location_url)
            req.raise_for_status()
            #print req.headers
            current_obs = ET.fromstring(req.content)
            ksgf_temp = float(current_obs.find('temp_f').text)
            print current_obs.find("location").text
            cur_obs_time = current_obs.find('observation_time_rfc822').text
            if last_obs_time != cur_obs_time:
                history.append([ksgf_temp,
                                current_obs.find('observation_time_rfc822').text,
                                time.strftime("%a, %d %b %Y %H:%M:%S -0600")])
                #speech.say("At {location}, the weather was {weather}. \
                #            It was {temp} degrees and the wind was {winds}".format(
                #            location=current_obs.find("location").text,
                #            weather=current_obs.find("weather").text,
                #            temp=current_obs.find('temp_f').text,
                #            winds=current_obs.find('wind_string').text))

                if len(history) > 25:
                    foo = history.pop(0)
                last_obs_time = cur_obs_time

            target_temp.value = ksgf_temp
            while run_counter < 6000:
                if signal.value > 0:
                    raise Exception
                time.sleep(0.5)
                run_counter += random.randint(1,20)
            run_counter = 0

        except requests.exceptions.RequestException as e:
            print "Requests exception"
            print type(e)
            print e
            time.sleep(10)

        except Exception as e:
            print "Other exception"
            print e
            break
        finally:
            pass
    print "Web process finishing"

def speak_weather(current_obs):
    pass

if __name__ == '__main__':
    manager = Manager()
    target_temp = manager.Value("d", -999.0)
    signal = manager.Value('h', 0)
    history = manager.list()
    serial_pipe = Pipe()
    serial_proc = Process(target=serial_stuff, args=(target_temp,signal,serial_pipe))
    serial_proc.start()
    web_pipe = Pipe()
    web_proc = Process(target=web_stuff, args=(target_temp,signal,web_pipe,history))
    web_proc.start()
    while True:
        try:
            data = raw_input(">>>")
            target_temp.value = float(data)
            #print web_q.get(False)
        except ValueError as e:
            if data == 'quit':
                break
            if data == "hist":
                for reading in history:
                    print reading
            if data == '':
                pass
            else:
                print e
        except KeyboardInterrupt:
            break
        except Exception as e:
            print e
            break

    signal.value = 1
    print "Waiting to close comport..."
    serial_proc.join()
    web_proc.join()
    print "Exiting process"
