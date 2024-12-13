"""
A simple tool to parse and plot the serial output of the DSO-138 with DLO-138 firmware.
Forked from: https://github.com/HummusPrince/DLO-138_plotter
Developed with the original DSO138 (without hardware modifications), therefore
this tool parses and plot data from only one analog channel. 
Possible to also compute FFT of the recieved data.

Usage: 
    python3 oscilloscope.py /dev/ttyUSB0 --fft
optional fft flag will generate two subplots one with the signal from DSO138 
and with the FFT. 

Author: JM
Date: 13/12/2024
"""


import argparse
import serial
import matplotlib.pyplot as plt
import numpy as np

from scipy.fft import fft, fftfreq
from time import sleep

BOUND_RATE = 115200


def get_data(port):
    """Initializes the serial port and recieves the data from DSO138

    Args:
        port (str): port with USB TTL converter (e.g., COM5 for windows, /dev/ttyUSB0 for ubuntu)

    Returns:
        list: recieved data from DSO138 as list of ascii characters
    """

    # initialize serial port 
    serial_port = serial.Serial(port, BOUND_RATE, timeout=1)
    serial_port.reset_input_buffer()

    print("waiting for data")

    buffer = bytes() # init the buffer in which the data will be read
    
    # wait for DSO138 to start sending data
    while serial_port.in_waiting == 0:
        sleep(0.1)
    print("receiving data")

    # in a loop read the data from the serial port into a buffer until no new data is recieved
    prev_buffer_size = 0
    while True:
        # update buffer
        if serial_port.in_waiting > 0:
            buffer += serial_port.read(serial_port.in_waiting)
        # exit condition
        if prev_buffer_size == len(buffer) and len(buffer) != 0:
            break
        prev_buffer_size = len(buffer)
        sleep(0.1)
    
    # split the data and conver to ascii
    raw_data = [str(line, 'ascii') for line in buffer.split(b'\r\n')]

    # close the serial port
    serial_port.close()
    print("data received")
    return raw_data
    
    
def parse_data(raw_data):
    """Parses the recieved data via serial port into a dictionary
    Only small adjustments of the original:
      https://github.com/HummusPrince/DLO-138_plotter

    Args:
        raw_data (list): data recieved through serial port (from fcn. get_data)

    Returns:
        dict: dictionary containing all data from DSO138 
    """
    plotdict = dict() 
    plotdict ['TscaleUnits'] = raw_data[2].split()[2][:2]
    plotdict['Tscale'] = float(raw_data[3].split()[-1])
    if plotdict['TscaleUnits'] == 'mS':
        plotdict['Tscale'] /= 1000
    plotdict['coupling'] = raw_data[4].split()[2].replace(",", "")
    plotdict['Vscale'] = raw_data[4].split()[4]
    plotdict['VscaleUnits'] = 'mV' if plotdict['Vscale'][-6] == 'm' else 'V'
    plotdict['VoltageStats'] = raw_data[8].strip().replace(', ','\n')
    plotdict['SignalStats'] = raw_data[9].strip().replace(', ','\n')
    # get channel 1 data and store it as numpy array
    plotdict['ch1'] = np.array([float(i.split('\t')[1]) for i in raw_data[12:-2]])
    # assert in case of not receiving all of the data
    assert len(plotdict['ch1']) == 2048
    return plotdict
    
    
def plot_signal(ax, plotdict):
    """Displays the (voltage) signal received from the DSO138 together with 
    the voltage and signal stats (user can specify otherwise by a 
    --no_stats argument flag, which is then stored in the plotdict) 

    Args:
        ax (matplotlib.axes): matplotlib axes onto which data will be plotted
        plotdict (dict): dictionary containing all data from DSO138 (obtained by fcn. parse_data)
    """
    time = [i * plotdict['Tscale']/25 for i in range(2048)]
    ax.plot(time, plotdict['ch1'], color = '#FFFF00', linewidth = 0.1, antialiased = False)
    ax.grid(color = '#404040', linewidth = 1, antialiased = True)
    ax.set_xlabel('time [{}]'.format(plotdict['TscaleUnits']))
    ax.set_ylabel('voltage [{}]'.format(plotdict['VscaleUnits']))
    ax.set_title("Signal")

    # adjust the x-axis range
    ax.set_xlim(0, max(time)) 
    xmin, xmax = ax.get_xlim()

    # display the voltage and signal stats (based on --no_stats argument)
    if not plotdict["no_stats"]:
        # adjust the y-axis range
        ymin, ymax = ax.get_ylim() 
        ymax += (ymax - ymin) * 0.3
        ax.set_ylim(ymin, ymax)

        ax.text(xmax*0.95, ymax*0.95, plotdict['VoltageStats'], fontsize = 8, ha = 'right', va = 'top', ma = 'left')
        ax.text(0.05*xmax, ymax*0.95, plotdict['SignalStats'], fontsize = 8, ha = 'left', va = 'top', ma = 'left')



def plot_fft(ax, plotdict):
    """Computes and displays FFT of the voltage signal received from DSO138.
    No windowing is applied. 
    TODO: add parameters to control FFT
    TODO: Welch's PSD computation for stochastic signals

    Args:
        ax (matplotlib.axes): matplotlib axes onto which data will be plotted
        plotdict (dict): dictionary containing all data from DSO138 (obtained by fcn. parse_data)
    """
    # get the time axis
    time = [i * plotdict['Tscale']/25 for i in range(2048)]
    # get the duration of the signal
    if plotdict["TscaleUnits"] == "uS":
        duration = time[-1] / 1e6 
    elif plotdict["TscaleUnits"] == "mS":
        duration = time[-1] / 1e3
    elif plotdict["TscaleUnits"] == "S":
        duration = time[-1]
    else:
        print("WARNING: something is really wrong")

    N = len(plotdict['ch1']) # number of samples
    T = duration/N # compute the sampling period

    # compute FFT
    # w = blackman(N)
    # yf = fft(data*w)
    yf = fft(plotdict['ch1'])
    xf = fftfreq(N, T)[:N//2]

    # plot the FFT data (normalized by the number of samples)
    ax.semilogy(xf[1:N//2], 2.0/N * np.abs(yf[1:N//2]), color = '#FFFF00', linewidth = 0.1, antialiased = False)
    ax.grid(color = '#404040', linewidth = 1, antialiased = True)
    ax.set_xlabel('frequency [Hz]')
    ax.set_ylabel('amplitude [{}]'.format(plotdict['VscaleUnits']))
    ax.set_title("FFT")
    ax.set_xlim(0, plotdict["xmax_FFT"])


def print_info(plotdict):
    """Displays the parameters or settings of the DSO138 together with 
    voltage statistics (Vmax, Vmin, Vavrm, Vpp, Vrms) and
    signal statistics (Freq, Cycle, PW, Duty)

    Args:
        plotdict (dict): parsed dictionary of received data (from fcn. parse_data) 
    """
    print("-"*60) # delimiter

    # display DSO138 settings/parameters
    print("Settings: {} coupling, \tresolution: {}, \tunits: {}, {}".format(
        plotdict["coupling"],  plotdict["Vscale"], plotdict["VscaleUnits"], plotdict["TscaleUnits"]))
    # display and parse voltage stats
    voltage_stats = plotdict["VoltageStats"].split("\n")
    for val in voltage_stats:
        parts = val.split(":")
        print("{}:\t\t{} {}".format(parts[0], parts[1], plotdict["VscaleUnits"]))
    # display and parse signal stats
    signal_stats = plotdict["SignalStats"].split("\n")
    for val in signal_stats:
        parts = val.split(":")
        if parts[0] == "Freq":
            print("{}:\t\t{} Hz".format(parts[0], parts[1]))
        else:
            print("{}:\t\t{}".format(parts[0], parts[1]))
    
    print("-"*60) # delimiter
    
    
if __name__ == "__main__":
    # parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=str, help="The port to use")
    parser.add_argument("-f", "--fft", action='store_true', help="Computes FFT of the data")
    parser.add_argument("-ns", "--no_stats", action='store_true', help="Computes FFT of the data")
    parser.add_argument("--xmax", type=int, default=4000, help="Limit to the frequencies of FFT")
    args = parser.parse_args()

    # main loop
    while True:
        # init serial port and wait for the data
        raw_data = get_data(args.port)
        # parse the recieved data
        plotdict = parse_data(raw_data)
        # show info about the DSO138 settings with voltage and signal stats
        print_info(plotdict)
        # update the plotdict with user arguments
        plotdict["xmax_FFT"] = args.xmax
        plotdict["no_stats"] = args.no_stats
    
        # --- plotting
        plt.style.use('dark_background')
        # plot signal with FFT
        if args.fft:
            fig, axs = plt.subplots(2, 1, figsize=(12, 7) , gridspec_kw={'height_ratios': [2, 1]})
            plot_signal(axs[0], plotdict)
            plot_fft(axs[1], plotdict)
        # plot only signal
        else:
            fig, axs = plt.subplots(1, 1, figsize=(12, 7))
            plot_signal(axs, plotdict)

        fig.subplots_adjust(hspace=0.5)
        fig.suptitle('Oscilloscope DLO-138', fontsize=16)
        # update plot
        plt.show()
        