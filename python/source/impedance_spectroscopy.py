# This Python file uses the following encoding: latin-1
#
# Copyright (c) 2016, the Cap authors.
#
# This file is subject to the Modified BSD License and may not be distributed
# without copyright and license information. Please refer to the file LICENSE
# for the text and further information on this license.

from matplotlib import pyplot
from numpy import real, imag, log10, absolute, angle, array, append, power,\
    sin, pi, sum, isclose, fft, mean, argsort
from warnings import warn
from copy import copy
from io import open  # to be able to use parameter ``encoding`` with Python2.7
from .data_helpers import initialize_data, report_data, save_data
from .peak_detection import peakdet
from .observer_pattern import Observer, Experiment
import pycap

__all__ = ['plot_nyquist', 'plot_bode',
           'fourier_analysis', 'retrieve_impedance_spectrum',
           'NyquistPlot', 'BodePlot', 'ECLabAsciiFile',
           'ElectrochemicalImpedanceSpectroscopy']


def _is_power_of_two(x):
    return (x != 0) and (x & (x - 1) == 0)


def plot_nyquist(data, figure=None, ls='r-s'):
    impedance = data['impedance']
    resistance = real(impedance)
    reactance = imag(impedance)
    plot_linewidth = 3
    label_fontsize = 30
    tick_fontsize = 20
    if figure:
        pyplot.figure(figure.number)
    else:
        pyplot.figure(figsize=(14, 14))
    pyplot.plot(resistance, -reactance, ls, lw=plot_linewidth)
    pyplot.axis('equal')
    pyplot.xlabel(r'$\mathrm{Resistance\ [\Omega]}$', fontsize=label_fontsize)
    pyplot.ylabel(r'$\mathrm{-Reactance\ [\Omega]}$', fontsize=label_fontsize)
    pyplot.gca().xaxis.set_tick_params(labelsize=tick_fontsize)
    pyplot.gca().yaxis.set_tick_params(labelsize=tick_fontsize)


def plot_bode(data):
    frequency = data['frequency']
    impedance = data['impedance']
    magnitude = 20 * log10(absolute(impedance))
    phase = angle(impedance, deg=True)
    label_fontsize = 30
    tick_fontsize = 20
    labelx = -0.05
    labely = 0.5
    plot_linewidth = 3
    f, axarr = pyplot.subplots(2, sharex=True, figsize=(16, 12))
    axarr[0].plot(frequency, magnitude, 'b-o', lw=plot_linewidth)
    axarr[0].set_xscale('log')
    axarr[0].set_ylabel(r'$\mathrm{Magnitude\ [dB]}$', fontsize=label_fontsize)
    axarr[0].get_yaxis().set_tick_params(labelsize=tick_fontsize)
    axarr[0].yaxis.set_label_coords(labelx, labely)
    axarr[1].plot(frequency, phase, 'g-o', lw=plot_linewidth)
    axarr[1].set_xscale('log')
    axarr[1].set_ylabel(r'$\mathrm{Phase\ [Degrees]}$',
                        fontsize=label_fontsize)
    axarr[1].set_xlabel(r'$\mathrm{Frequency\ [Hz]}$', fontsize=label_fontsize)
    axarr[1].get_yaxis().set_tick_params(labelsize=tick_fontsize)
    axarr[1].get_xaxis().set_tick_params(labelsize=tick_fontsize)
    axarr[1].yaxis.set_label_coords(labelx, labely)


def run_one_cycle(device, ptree):
    frequency = ptree.get_double('frequency')
    dc_voltage = ptree.get_double('dc_voltage')
    harmonics = array(ptree.get_array_int('harmonics'))
    ac_amplitudes = array(ptree.get_array_double('amplitudes'))
    phases = array(ptree.get_array_double('phases')) * pi / 180
    steps_per_cycle = ptree.get_int('steps_per_cycle')
    cycles = ptree.get_int('cycles')
    time_step = 1. / (frequency * steps_per_cycle)
    time = 0.0
    data = initialize_data()
    for cycle in range(cycles):
        for step in range(steps_per_cycle):
            time += time_step
            excitation_signal = dc_voltage + sum(ac_amplitudes *
                                                 sin(2 * pi * harmonics * frequency *
                                                     time + phases))
            device.evolve_one_time_step_linear_voltage(time_step,
                                                       excitation_signal)
            report_data(data, time, device)

    return data


def retrieve_impedance_spectrum(fin):
    path = 'eis_data'
    eis_data = {'frequency': array([], dtype=float),
                'impedance': array([], dtype=complex)}
    for key in fin[path].keys():
        cycling_data = fin[path][key]
        f, Z = fourier_analysis(cycling_data)
        eis_data['frequency'] = append(eis_data['frequency'], f)
        eis_data['impedance'] = append(eis_data['impedance'], Z)
    sort = argsort(eis_data['frequency'])
    eis_data['frequency'] = eis_data['frequency'][sort]
    eis_data['impedance'] = eis_data['impedance'][sort]
    eis_data['frequency'] = eis_data['frequency'][::-1]
    eis_data['impedance'] = eis_data['impedance'][::-1]

    return eis_data


def fourier_analysis(data, ptree=None):
    time = data['time']
    current = data['current']
    voltage = data['voltage']

    # inspect data
    n = len(time)  # normalization factor for fft
    assert len(current) == n
    assert len(voltage) == n
    d = time[1] - time[0]  # inverse of the sampling rate
    # check sampling spacing is the same everywhere
    for i in range(n - 1):
        assert isclose(time[i + 1] - time[i], d, atol=1e-10, rtol=1e-10)

    # truncate signals
    if ptree:
        steps_per_cycle = ptree.get_int('steps_per_cycle')
        cycles = ptree.get_int('cycles')
        ignore_cycles = ptree.get_int('ignore_cycles')
        assert cycles > ignore_cycles
        assert n == cycles * steps_per_cycle
        time = time[ignore_cycles * steps_per_cycle:]
        current = current[ignore_cycles * steps_per_cycle:]
        voltage = voltage[ignore_cycles * steps_per_cycle:]
    else:
        time = time[int(n / 2):]
        current = current[int(n / 2):]
        voltage = voltage[int(n / 2):]

    n = len(time)
    assert len(current) == n
    assert len(voltage) == n

    if not _is_power_of_two(n):
        warn(
            "(cycles-ignore_cycles)*steps_per_cycles is not a "
            "power of 2 (most efficient for the fourier analysis)",
            RuntimeWarning)

    # perform the actual fourrier analaysis
    fft_current = fft.rfft(current) / n
    fft_voltage = fft.rfft(voltage) / n
    fft_frequency = fft.rfftfreq(n, d)

    # find the excited harmonics
    if ptree:
        harmonics = array(ptree.get_array_int('harmonics'))
        peak_indices = harmonics * (cycles - ignore_cycles)
    else:
        mx, mn = peakdet(absolute(fft_voltage), mean(absolute(fft_current)))
        peak_indices = int(mx[:, 0])
        mx, mn = peakdet(absolute(fft_voltage), mean(absolute(fft_current)))
        assert peak_indices == mx[:, 0]

    frequency = fft_frequency[peak_indices]
    impedance = fft_voltage[peak_indices] / fft_current[peak_indices]

    return [frequency, impedance]


class NyquistPlot(Observer):
    '''Nyquist plot.

    The frequency-dependent impedance Z(f) is represented as a complex number:
        Z(f) = R + jX
    In a Nyquist plot, the real part of the impedance R = real(Z) is plotted on
    the X-axis and the imaginary part X = imag(Z) on the Y-axis. R and X are
    called resistance and reactance, respectively. Both are expressed in ohm.

    Nyquist plots have one major shortcoming. When looking at any data point
    on the complex plane, it is impossible to tell what frequency was used to
    record that point.

    See also
    --------
    BodePlot
    '''
    def __new__(cls, *args, **kwargs):
        return object.__new__(NyquistPlot)

    def __init__(self, filename=None):
        self._figure = pyplot.figure(figsize=(14, 14))
        self._filename = filename

    def update(self, subject, *args, **kwargs):
        plot_nyquist(subject._data, figure=self._figure)
        if self._filename is not None:
            pyplot.savefig(self._filename, bbox_inches='tight')


Observer._builders['NyquistPlot'] = NyquistPlot


class BodePlot(Observer):
    '''Bode plot.

    A Bode plot is another popular presentation method for impedance spectra.
    The impedance is plotted with frequency on the X-axis in log scale and
    absolute values of the impedance in dB, 20*log10(|Z|), and the phase shift
    in degree, arg(Z), on the Y-axis.

    Unlike the Nyquist plot, the Bode plot does show frequency information.

    See also
    --------
    NyquistPlot
    '''
    def __new__(cls, *args, **kwargs):
        return object.__new__(BodePlot)

    def __init__(self, filename=None):
        raise NotImplementedError

    def update(self, subject, *args, **kwargs):
        raise NotImplementedError


Observer._builders['BodePlot'] = BodePlot


class ECLabAsciiFile(Observer):
    '''Exports a text format file recognised by EC-Lab software.

    Attributes
    ----------
    _filename : string
        Name of the file to be exported.
    _unformated_headers : list of strings
        Headers with a number of placeholders that are meant to be be
        formated before exporting to the output file.
    _line_template : string
        Template for a line that will be written. It contains replacement fields
        and is meant to be formatted.
    _encoding : string
        I had an issue with Python 3.5 to decode byte 0xb2.

    See Also
    --------
    ElectrochemicalImpedanceSpectroscopy
    '''
    def __new__(cls, *args, **kwargs):
        return object.__new__(ECLabAsciiFile)

    def __init__(self, filename):
        self._filename = filename
        self._encoding = 'latin-1'
        # building the headers
        self._unformated_headers = [
            u'EC-Lab ASCII FILE\r\n',
            u'Nb header lines : {header_lines}\r\n',
            u'\r\n',
            u'Potentio Electrochemical Impedance Spectroscopy\r\n',
            u'\r\n',
            u'Generated using Cap version "{git_commit_hash}"\r\n',
            u'See {git_remote_url}\r\n',
            u'\r\n',
            u'Anode\r\n',
            u'-----\r\n',
            u'geometric area           [cm�]    {geometric_area}\r\n',
            u'thickness                [cm]     {anode_electrode_thickness}\r\n',
            u'double layer capacitance [�F/cm�] {anode_electrode_double_layer_capacitance}\r\n',
            u'interfacial surface area [cm�]    {anode_electrode_interfacial_surface_area}\r\n',
            u'mass active material     [g]      {anode_electrode_mass_of_active_material}\r\n',
            u'\r\n',
            u'Cathode\r\n',
            u'-------\r\n',
            u'geometric area           [cm�]    {geometric_area}\r\n',
            u'thickness                [cm]     {cathode_electrode_thickness}\r\n',
            u'double layer capacitance [�F/cm�] {cathode_electrode_double_layer_capacitance}\r\n',
            u'interfacial surface area [cm�]    {cathode_electrode_interfacial_surface_area}\r\n',
            u'mass active material     [g]      {cathode_electrode_mass_of_active_material}\r\n',
            u'\r\n',
            u'freq/Hz\tRe(Z)/Ohm\t-Im(Z)/Ohm\t|Z|/Ohm\tPhase(Z)/deg\t'
            u'time/s\t<Ewe>/V\t<I>/mA\tCs/�F\tCp/�F\t'
            u'cycle number\tI Range\t|Ewe|/V\t|I|/A\t'
            u'Re(Y)/Ohm-1\tIm(Y)/Ohm-1\t|Y|/Ohm-1\tPhase(Y)/deg\r\n',
        ]
        # build a template for each line in the results
        self._line_template = ''
        for i in range(18):
            self._line_template += '{left}{0}:{format_spec}{right}{separator}'\
                .format(i, format_spec='{format_spec}',
                        left='{', right='}', separator='\t')
        self._line_template += '\r\n'

    def update(self, subject, *args, **kwargs):
        def m2_to_cm2(x): return 10000 * x

        def kg_to_g(x): return 1000 * x
        with open(self._filename, mode='wb') as fout:
            NaN = 255
            extra_data = subject._extra_data
            headers = u''
            separator = '|X|'
            for line in self._unformated_headers:
                headers += line + separator
            headers = headers.rstrip(separator).format(
                header_lines=len(self._unformated_headers),
                git_commit_hash=pycap.__git_commit_hash__,
                git_remote_url=pycap.__git_remote_url__,
                geometric_area=extra_data['geometric_area'],
                anode_electrode_thickness=extra_data[
                    'anode_electrode_thickness'],
                anode_electrode_double_layer_capacitance=extra_data[
                    'anode_electrode_double_layer_capacitance'],
                anode_electrode_interfacial_surface_area=m2_to_cm2(
                    extra_data['anode_electrode_interfacial_surface_area']),
                anode_electrode_mass_of_active_material=kg_to_g(
                    extra_data['anode_electrode_mass_of_active_material']),
                cathode_electrode_thickness=extra_data[
                    'cathode_electrode_thickness'],
                cathode_electrode_double_layer_capacitance=extra_data[
                    'cathode_electrode_double_layer_capacitance'],
                cathode_electrode_interfacial_surface_area=m2_to_cm2(
                    extra_data['cathode_electrode_interfacial_surface_area']),
                cathode_electrode_mass_of_active_material=kg_to_g(
                    extra_data['cathode_electrode_mass_of_active_material']),
            ).split(separator)

            # write headers
            for line in headers:
                fout.write(line.encode(self._encoding))

            # write data
            n = subject._data['frequency'].size
            for i in range(n):
                f = subject._data['frequency'][i]
                Z = subject._data['impedance'][i]
                Y = 1.0 / Z
                line = self._line_template.format(
                    float(f),
                    float(real(Z)),
                    -float(imag(Z)),
                    float(absolute(Z)),
                    float(angle(Z, deg=True)),
                    NaN,
                    NaN,
                    NaN,
                    NaN,
                    NaN,
                    NaN,
                    NaN,
                    NaN,
                    NaN,
                    float(real(Y)),
                    float(imag(Y)),
                    float(absolute(Y)),
                    float(angle(Y, deg=True)),
                    format_spec='.7e'
                )
                fout.write(line.encode(self._encoding))


Observer._builders['ECLabAsciiFile'] = ECLabAsciiFile


class ElectrochemicalImpedanceSpectroscopy(Experiment):
    '''ElectrochemicalImpedanceSpectroscopy (EIS)

    Measures the complex impedance of an energy storage device as a function of
    the frequency,

    Attributes
    ----------
    _frequencies : numpy.array of float
    _ptree : PropertyTree
    _data : dict
        Stores the frequency as a numpy.array of floating point numbers
        and the impedance as a numpy.array of complex numbers.
    _extra_data : dict
        Stores the information computed by the postprocessor and some of the
        input data that need to be saved.

    Examples
    --------
    ptree = PropertyTree()
    ptree.parse_info(eis.info)
    eis = Experiment(ptree)

    observer = NyquistPlot("nyquist_plot.png")
    eis.attach(observer)

    eis.run(device)

    See Also
    --------
    NyquistPlot, BodePlot
    '''
    def __new__(cls, *args, **kwargs):
        return object.__new__(ElectrochemicalImpedanceSpectroscopy)

    def __init__(self, ptree, frequencies=None):
        '''
        Parameters
        ----------
        ptree : PropertyTree
        frequencies : array_like, optional
            Specify the frequencies. If provided will be used to initialize a
            numpy.array of float.
        '''
        Experiment.__init__(self)
        if frequencies is None:
            frequency_upper_limit = ptree.get_double('frequency_upper_limit')
            frequency_lower_limit = ptree.get_double('frequency_lower_limit')
            steps_per_decade = ptree.get_int('steps_per_decade')
            frequencies = []
            frequency = frequency_upper_limit
            # we were having floating point precision issues and the lower bound
            # was often excluded of the range. so instead of comparing against
            # it, we relax with one percent of the distance to the next point on
            # the log scale.
            while frequency >= frequency_lower_limit * (1 + 0.01 * (1.0 / power(10.0, 1.0 / steps_per_decade) - 1)):
                frequencies.append(frequency)
                frequency /= power(10.0, 1.0 / steps_per_decade)
        self._frequencies = array(frequencies, dtype=float)
        self._ptree = copy(ptree)
        self.reset()

    def reset(self):
        self._data = {
            'frequency': array([], dtype=float),
            'impedance': array([], dtype=complex)
        }

    def run(self, device, fout=None):
        self._extra_data = device.inspect()
        for frequency in self._frequencies:
            self._ptree.put_double('frequency', frequency)
            data = run_one_cycle(device, self._ptree)
            if fout:
                path = 'eis_data'
                path += '/frequency=' + str(frequency) + 'Hz'
                save_data(data, path, fout)
            f, Z = fourier_analysis(data, self._ptree)
            self._data['frequency'] = append(self._data['frequency'], f)
            self._data['impedance'] = append(self._data['impedance'], Z)
            self.notify()


for alias in ['EIS', 'ElectrochemicalImpedanceSpectroscopy']:
    Experiment._builders[alias] = ElectrochemicalImpedanceSpectroscopy
