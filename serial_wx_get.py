import serial
from multiprocessing import Process, Pipe, Manager
import time
import sys
import random
#import speech
import requests
import xml.etree.ElementTree as ET
from httpcache import CachingHTTPAdapter
import traceback
#import pywintypes

def serial_output_proc(target_temp, term_signal):
    com = serial.serial_for_url("COM10", timeout=2)
    line_buffer = ""
    output_temp = target_temp.value
    while True:
        try:
            #print "Reading serial"
            byte = com.read(1)
            if term_signal.value > 0:
                raise Exception
            if byte == '\r':
                #print line_buffer #Or pass the data somewhere else
                if output_temp < -998 or target_temp.value < -998:
                    foo = com.write("E000\r\n")
                    output_temp = target_temp.value
                elif output_temp < 0:
                    foo = com.write("{0}\r\n".format(output_temp))
                else:
                    foo = com.write("+{0}\r\n".format(output_temp))
                if output_temp < -998 and target_temp.value >= -998:
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

def serial_input_proc(target_temp, term_signal, p, history):
    com = serial.serial_for_url("COM9", timeout=2)
    serial_temp = ''
    line_buffer = ""
    byte = ''

    def get_temp_by_char(line_buffer, byte):
        while True:
            try:
                if term_signal.value > 0:
                    raise Exception
                foo = com.write('\r')
                byte = com.read(1)
                if byte == '\r':
                    #print line_buffer
                    string_temp = line_buffer
                    line_buffer = ''
                    temperature = float(string_temp)
                else:
                    line_buffer = line_buffer + byte
                    raise ValueError
            except ValueError:
                #print "Error"
                continue
            except Exception as e:
                com.close()
                print traceback.format_exc()
                break
            else:
                #print temperature
                #sys.stdout.write(" | " + string_temp)
                history.append(['COM', temperature, time.strftime("%a, %d %b %Y %H:%M:%S -0600") ])
                if len(history) > 100:
                    foo = history.pop(0)
                if p.poll(32):
                    print p.recv()

    def get_temp_by_timeout(serial_temp):
        while True:
            try:
                #print "Reading serial"
                foo = com.write('\r')
                serial_temp = com.read(10)
                if term_signal.value > 0:
                    raise Exception
                temperature = float(serial_temp)
            except ValueError:
                continue
            except Exception as e:
                com.close()
                print traceback.format_exc()
                break
            else:
                print temperature

    #get_temp_by_char(line_buffer, byte)
    print "Serial input finishing"

def web_process(target_temp, term_signal, p, history):
    s = requests.Session()
    s.mount('http://', CachingHTTPAdapter())
    last_obs_time = ''
    location = "KSGF"
    back_off_ctr = 0
    refresh_requested = False
    speech_flag = True

    def get_temperature(location, session):
        location_url = "http://www.weather.gov/data/current_obs/{location}.xml".format(location=location)
        req = session.get(location_url)
        req.raise_for_status()
        #print req.headers

        try:
            current_obs = ET.fromstring(req.content)
            obs_data = {'temp_f':None,
                        'observation_time_rfc822':None,
                        'location':None}
                        #'weather':None,
                        #'wind_string':None}
            for key in obs_data.keys():
                obs_data[key] = current_obs.find(key).text

        except AttributeError as e:
            #To do: better handling if the data returned is not understood
            print "Something went wrong with the weather data, a value is missing"
            print key
            print traceback.format_exc()
        finally:
            return obs_data

    def speak_weather(**kwargs):
        pass
        #for key in kwargs.keys():
        #    print key, kwargs[key]
        #speech.say("At {location}, the weather was {weather}. \
        #            It was {temp_f} degrees and the wind was {wind_string}".format(**kwargs).replace(
        #                 'KT)', 'knots)'))

    while True:
        try:
            if back_off_ctr > 0:
                back_off_time = random.randrange(0,(2**back_off_ctr - 1)) * 10
                print "Retry in {0} seconds".format(back_off_time)
            else:
                back_off_time = 0
            refresh_requested = p.poll(300 + random.randrange(0,120) + back_off_time)
            if refresh_requested:
                data = p.recv()
                if data[0] == 'refresh':
                    last_obs_time = ''
                    s.mount('http://', CachingHTTPAdapter())
                elif data[0] == 'Location':
                    last_obs_time = ''
                    location = data[1].upper()
                elif data[0] == 'speech':
                    speech_flag = data[1]
                    p.send("Speech output set {0}".format(data[1]))
                else:
                    pass
            if term_signal.value > 0:
                raise Exception
            obs_data = get_temperature(location, s)
            if last_obs_time != obs_data['observation_time_rfc822'] and \
                                obs_data['observation_time_rfc822'] is not None:
                #print "Temperature updated"
                history.append([location, obs_data['temp_f'], obs_data['observation_time_rfc822'],
                                time.strftime("%a, %d %b %Y %H:%M:%S -0600")])
                if len(history) > 48:
                    foo = history.pop(0)
                #print temp
                target_temp.value = float(obs_data['temp_f'])
                if refresh_requested:
                    p.send("Temperature updated\n{0}\n{1}".format(obs_data['location'], obs_data['temp_f']))
                if speech_flag:
                    speak_weather(**obs_data)

        except requests.exceptions.HTTPError as e:
            print "Requests exception"
            if e.response.status_code == 404:
                print "The url {url} is not found".format(url=e.response.url)
            else:
                print type(e)
                print e
                print traceback.format_exc()
            back_off_ctr += 1
            continue
        except  requests.exceptions.ConnectionError as e:
            print "Connection problem, lost Internet connectivity?"
            print e
            back_off_ctr += 1
            continue

        #except pywintypes.com_error as e:
        #    print "Win32 error"
        #    print type(e)
        #    print traceback.format_exc()
        #    continue

        except ValueError:
            print "Bad temperature value"
            continue
        except Exception as e:
            print e
            break
        else:
            back_off_ctr = 0
            last_obs_time = obs_data['observation_time_rfc822']
            #print "Success!"
        finally:
            pass
    print "Exiting web process..."

def get_weather_stations():
    r = requests.get('http://w1.weather.gov/xml/current_obs/index.xml')
    #print r.content
    stations_dict = {}
    try:
        root = ET.fromstring(r.content)
        for station in root.findall('station'):
            state = station.find('state').text
            if state in stations_dict:
                stations_dict[state].append({'id':station.find('station_id').text,
                                             "name":station.find('station_name').text})
            else:
                stations_dict[state] = []
            #print station.find('state').text, station.find('station_id').text
    except:
        print "Couldn't retrieve station list"
    #print stations_dict
    return stations_dict

if __name__ == '__main__':
    manager = Manager()
    target_temp = manager.Value("d", -999.0)
    term_signal = manager.Value('h', 0)
    #web_run_ctr = manager.Value("d", 6000)
    history = manager.list()
    serial_history = manager.list()
    serial_in_pipe, serial_in_pipe_child = Pipe()
    serial_in = Process(target=serial_input_proc, args=(target_temp, term_signal, serial_in_pipe_child, serial_history))
    serial_in.start()
    serial_out = Process(target=serial_output_proc, args=(target_temp,term_signal))
    serial_out.start()
    web_pipe, web_pipe_child= Pipe()
    web_proc = Process(target=web_process, args=(target_temp,term_signal,web_pipe_child,history))
    #web_proc = Process(target=web_stuff, args=(target_temp,signal,web_pipe,history,web_run_ctr))
    web_proc.start()
    web_pipe.send(['location', 'KSGF'])
    #serial_in_pipe.send('Begin')
    if web_pipe.poll(2):
        print web_pipe.recv()
    stations = get_weather_stations()
    #print stations['MO']
    while True:
        try:
            if web_pipe.poll(0.1):
                print web_pipe.recv()
            data = raw_input(">>>")
            target_temp.value = float(data)
            print "Current temperature value is", target_temp.value
        except ValueError as e:
            if data == 'quit' or data == 'exit':
                break
            elif data == 'help':
                print """**** Help
        'quit' => exit the program
        'hist' => get a history of temperature readings
        'set XXXX' => set the weather location to XXXX
        'refresh' => force refresh
        'stations XX' => show list of stations in a state
         type a number => set the temperature to 'number'
        'help' => this page
"""
            elif data == "hist":
                print "Location-Temp--Observation Time--------------------Downloaded Time---------"
                for reading in history:
                    print reading
                continue
            elif data == "comhist":
                for reading in serial_history:
                    #sys.stdout.write(' | ' + repr(reading[1]))
                    print reading
                #print ''
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
                continue
            elif data[0:8] == 'stations':
                state = data[9:].upper().strip()
                print state
                if state in stations:
                    for station in stations[state]:
                        print "{id} - {name}".format(**station)
                else:
                    print "State not found"
                continue
            else:
                print "I didn't understand that, maybe try 'help'?"
                print data[0:7]
                #print e.message
                continue
        except KeyboardInterrupt:
            break
        except Exception as e:
            print e
            break
        finally:
            pass

    term_signal.value = 1
    web_pipe.send("Exit")
    serial_in_pipe.send("Exit")
    print "Waiting to close comport..."
    serial_in.join()
    serial_out.join()
    web_proc.join()
    print "Exiting process"
