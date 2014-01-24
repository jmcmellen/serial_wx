import serial
from multiprocessing import Process, Pipe, Manager
import time
import random
import speech
import requests
import xml.etree.ElementTree as ET
from httpcache import CachingHTTPAdapter
import traceback
import pywintypes

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

def web_process(target_temp, signal, p, history):
    s = requests.Session()
    s.mount('http://', CachingHTTPAdapter())
    last_obs_time = ''
    location = "KSGF"
    back_off_ctr = 0
    refresh_requested = False
    speech_flag = False

    def get_temperature(location, session):
        location_url = "http://www.weather.gov/data/current_obs/{location}.xml".format(location=location)
        req = session.get(location_url)
        req.raise_for_status()
        #print req.headers
        current_obs = ET.fromstring(req.content)
        temp = float(current_obs.find('temp_f').text)
        loc_text = current_obs.find("location").text
        weather = current_obs.find('weather').text
        winds = current_obs.find('wind_string').text
        cur_obs_time = current_obs.find('observation_time_rfc822').text
        return {'temp':temp,
                    'loc_text':loc_text,
                    'weather':weather,
                    'winds':winds,
                    'cur_obs_time':cur_obs_time}

    def speak_weather(**kwargs):
        #for key in kwargs.keys():
        #    print key, kwargs[key]
        speech.say("At {loc_text}, the weather was {weather}. \
                    It was {temp} degrees and the wind was {winds}".format(**kwargs).replace(
                         'KT)', 'knots)'))

    while True:
        try:
            if back_off_ctr > 0:
                back_off_time = random.randrange(0,(2**back_off_ctr - 1)) * 10
                print back_off_time
            else:
                back_off_time = 0
            refresh_requested = p.poll(300 + random.randrange(0,120) + back_off_time)
            if refresh_requested:
                data = p.recv()
                if data[0] == 'refresh':
                    last_obs_time = ''
                elif data[0] == 'location':
                    last_obs_time = ''
                    location = data[1].upper()
                elif data[0] == 'speech':
                    speech_flag = data[1]
                    p.send("Speech output set {0}".format(data[1]))
                else:
                    pass
            if signal.value > 0:
                raise Exception
            obs_data = get_temperature(location, s)
            if last_obs_time != obs_data['cur_obs_time']:
                #print "Temperature updated"
                history.append([location, obs_data['temp'], obs_data['cur_obs_time'],
                                time.strftime("%a, %d %b %Y %H:%M:%S -0600")])
                #print temp
                target_temp.value = obs_data['temp']
                last_obs_time = obs_data['cur_obs_time']
                #print "temp updated", loc_text, temp
                if refresh_requested:
                    p.send("Temperature updated\n{0}\n{1}".format(obs_data['loc_text'], obs_data['temp']))
                if speech_flag:
                    speak_weather(**obs_data)

        except requests.exceptions.RequestException as e:
            print "Requests exception"
            if e.response.status_code == 404:
                print "The url {url} is not found".format(url=e.response.url)
            else:
                print type(e)
                print e
                print traceback.format_exc()
            back_off_ctr += 1
            continue

        except pywintypes.com_error as e:
            print "Win32 error"
            print type(e)
            print traceback.format_exc()
            continue

        except Exception as e:
            print e
            break
        else:
            back_off_ctr = 0
        finally:
            pass
    print "Exiting web process..."

if __name__ == '__main__':
    manager = Manager()
    target_temp = manager.Value("d", -999.0)
    signal = manager.Value('h', 0)
    #web_run_ctr = manager.Value("d", 6000)
    history = manager.list()
    serial_pipe = Pipe()
    serial_proc = Process(target=serial_stuff, args=(target_temp,signal,serial_pipe))
    serial_proc.start()
    web_pipe, web_pipe_child= Pipe()
    web_proc = Process(target=web_process, args=(target_temp,signal,web_pipe_child,history))
    #web_proc = Process(target=web_stuff, args=(target_temp,signal,web_pipe,history,web_run_ctr))
    web_proc.start()
    web_pipe.send(['location', 'KSGF'])
    if web_pipe.poll(2):
        print web_pipe.recv()
    while True:
        try:
            if web_pipe.poll(0.1):
                print web_pipe.recv()
            data = raw_input(">>>")
            target_temp.value = float(data)
            print "Current temperature value is", target_temp.value
        except ValueError as e:
            if data == 'quit':
                break
            elif data == 'help':
                print """**** Help
        'quit' => exit the program
        'hist' => get a history of temperature readings
        'set XXXX' => set the weather location to XXXX
        'refresh' => force refresh
        'speech [on|off]' => turn speech on or off
         type a number => set the temperature to 'number'
        'help' => this page
"""
            elif data == "hist":
                print "Location-Temp--Observation Time--------------------Downloaded Time---------"
                for reading in history:
                    print reading
                continue
            elif data == '':
                print "Current temperature value is", target_temp.value
                continue
            elif data == 'refresh':
                print "Refreshing"
                web_pipe.send(['refresh',])
                if web_pipe.poll(2):
                    print web_pipe.recv()
                continue
            elif data[0:3] == 'set':
                print "Setting to " + data[4:]
                web_pipe.send(['location',data[4:]])
                if web_pipe.poll(2):
                    print web_pipe.recv()
                continue
            elif data[0:6] == 'speech':
                if data[7:].strip() == 'on':
                    web_pipe.send(['speech', True])
                else:
                    web_pipe.send(['speech', False])
                if web_pipe.poll(2):
                    print web_pipe.recv()
            else:
                print "I didn't understand that, maybe try 'help'?"
                #print e.message
                continue
        except KeyboardInterrupt:
            break
        except Exception as e:
            print e
            break
        finally:
            pass

    web_pipe.send("Exit")
    signal.value = 1
    print "Waiting to close comport..."
    serial_proc.join()
    web_proc.join()
    print "Exiting process"
