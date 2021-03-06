# Copyright (c) 2016, the Cap authors.
#
# This file is subject to the Modified BSD License and may not be distributed
# without copyright and license information. Please refer to the file LICENSE
# for the text and further information on this license.


# Select a non-interactive backend for Matplotlib
# NOTE: must be done before importing matplotlib.pyplot
import matplotlib
matplotlib.use('PS')

from pycap import PropertyTree, EnergyStorageDevice, Experiment,\
    ECLabAsciiFile, NyquistPlot
from pycap import retrieve_impedance_spectrum,\
    fourier_analysis, initialize_data
from numpy import inf, linalg, pi, log10, absolute, angle,\
    array, ones, cos, sin, equal
from warnings import catch_warnings, simplefilter
from h5py import File
from io import open
import unittest


class ImpedanceSpectroscopyTestCase(unittest.TestCase):

    def test_fourier_analysis(self):
        ptree = PropertyTree()
        ptree.put_int('steps_per_cycle', 3)
        ptree.put_int('cycles', 1)
        ptree.put_int('ignore_cycles', 0)
        ptree.put_string('harmonics', '1')
        # uninitialized data
        data = {}
        self.assertRaises(KeyError, fourier_analysis, data, ptree)
        # empty data
        data = initialize_data()
        self.assertRaises(IndexError, fourier_analysis, data, ptree)
        # bad data
        data['time'] = array([1, 2, 3], dtype=float)
        data['current'] = array([4, 5, 6], dtype=float)
        data['voltage'] = array([7, 8], dtype=float)
        self.assertRaises(AssertionError, fourier_analysis, data, ptree)
        # poor data (size not a power of 2)
        data['voltage'] = array([7, 8, 9], dtype=float)
        with catch_warnings():
            simplefilter("error")
            self.assertRaises(RuntimeWarning, fourier_analysis, data, ptree)
        # data unchanged after analyze
        dummy = array([1, 2, 3, 4, 5, 6, 7, 8], dtype=float)
        data['time'] = dummy
        data['current'] = dummy
        data['voltage'] = dummy
        # ptree needs to be updated
        self.assertRaises(AssertionError, fourier_analysis, data, ptree)
        ptree.put_int('steps_per_cycle', 4)
        ptree.put_int('cycles', 2)
        ptree.put_int('ignore_cycles', 0)
        fourier_analysis(data, ptree)
        self.assertTrue(all(equal(data['time'], dummy)))
        self.assertTrue(all(equal(data['current'], dummy)))
        self.assertTrue(all(equal(data['voltage'], dummy)))

    def test_retrieve_data(self):
        ptree = PropertyTree()
        ptree.put_string('type', 'SeriesRC')
        ptree.put_double('series_resistance', 100e-3)
        ptree.put_double('capacitance', 2.5)
        device = EnergyStorageDevice(ptree)

        ptree = PropertyTree()
        ptree.put_string('type', 'ElectrochemicalImpedanceSpectroscopy')
        ptree.put_double('frequency_upper_limit', 1e+2)
        ptree.put_double('frequency_lower_limit', 1e-1)
        ptree.put_int('steps_per_decade', 1)
        ptree.put_int('steps_per_cycle', 64)
        ptree.put_int('cycles', 2)
        ptree.put_int('ignore_cycles', 1)
        ptree.put_double('dc_voltage', 0)
        ptree.put_string('harmonics', '3')
        ptree.put_string('amplitudes', '5e-3')
        ptree.put_string('phases', '0')
        eis = Experiment(ptree)

        with File('trash.hdf5', 'w') as fout:
            eis.run(device, fout)
        spectrum_data = eis._data

        with File('trash.hdf5', 'r') as fin:
            retrieved_data = retrieve_impedance_spectrum(fin)

        print(spectrum_data['impedance'] - retrieved_data['impedance'])
        print(retrieved_data)
        self.assertEqual(linalg.norm(spectrum_data['frequency'] -
                                     retrieved_data['frequency'], inf), 0.0)
        # not sure why we don't get equality for the impedance
        self.assertLess(linalg.norm(spectrum_data['impedance'] -
                                    retrieved_data['impedance'], inf), 1e-10)

    def test_setup_frequency_range(self):
        ptree = PropertyTree()
        ptree.put_string('type', 'ElectrochemicalImpedanceSpectroscopy')
        # specify the upper and lower bounds of the range
        # the number of points per decades controls the spacing on the log
        # scale
        ptree.put_double('frequency_upper_limit', 1e+2)
        ptree.put_double('frequency_lower_limit', 1e-1)
        ptree.put_int('steps_per_decade', 3)
        eis = Experiment(ptree)
        print(eis._frequencies)
        f = eis._frequencies
        self.assertEqual(len(f), 10)
        self.assertAlmostEqual(f[0], 1e+2)
        self.assertAlmostEqual(f[3], 1e+1)
        self.assertAlmostEqual(f[9], 1e-1)
        # or directly specify the frequencies
        frequencies = [3, 2e3, 0.1]
        eis = Experiment(ptree, frequencies)
        self.assertTrue(all(equal(frequencies, eis._frequencies)))

    def test_verification_with_equivalent_circuit(self):
        R = 50e-3   # ohm
        R_L = 500   # ohm
        C = 3       # farad
        # setup EIS experiment
        ptree = PropertyTree()
        ptree.put_string('type', 'ElectrochemicalImpedanceSpectroscopy')
        ptree.put_double('frequency_upper_limit', 1e+4)
        ptree.put_double('frequency_lower_limit', 1e-6)
        ptree.put_int('steps_per_decade', 3)
        ptree.put_int('steps_per_cycle', 1024)
        ptree.put_int('cycles', 2)
        ptree.put_int('ignore_cycles', 1)
        ptree.put_double('dc_voltage', 0)
        ptree.put_string('harmonics', '3')
        ptree.put_string('amplitudes', '5e-3')
        ptree.put_string('phases', '0')
        eis = Experiment(ptree)
        # setup equivalent circuit database
        device_database = PropertyTree()
        device_database.put_double('series_resistance', R)
        device_database.put_double('parallel_resistance', R_L)
        device_database.put_double('capacitance', C)
        # analytical solutions
        Z = {}
        Z['SeriesRC'] = lambda f: R + 1 / (1j * C * 2 * pi * f)
        Z['ParallelRC'] = lambda f: R + R_L / (1 + 1j * R_L * C * 2 * pi * f)
        for device_type in ['SeriesRC', 'ParallelRC']:
            # create a device
            device_database.put_string('type', device_type)
            device = EnergyStorageDevice(device_database)
            # setup experiment and measure
            eis.reset()
            eis.run(device)
            f = eis._data['frequency']
            Z_computed = eis._data['impedance']
            # compute the exact solution
            Z_exact = Z[device_type](f)
            # ensure the error is small
            max_phase_error_in_degree = linalg.norm(
                angle(Z_computed) * 180 / pi - angle(Z_exact) * 180 / pi,
                inf)
            max_magniture_error_in_decibel = linalg.norm(
                20 * log10(absolute(Z_exact)) - 20 *
                log10(absolute(Z_computed)),
                inf)
            print(device_type)
            print(
                '-- max_phase_error_in_degree = {0}'.format(max_phase_error_in_degree))
            print(
                '-- max_magniture_error_in_decibel = {0}'.format(max_magniture_error_in_decibel))
            self.assertLessEqual(max_phase_error_in_degree, 1)
            self.assertLessEqual(max_magniture_error_in_decibel, 0.2)

    def test_export_eclab_ascii_format(self):
        # define dummy experiment
        # it is quicker than building an actual EIS experiment
        class DummyExperiment(Experiment):

            def __new__(cls, *args, **kwargs):
                return object.__new__(DummyExperiment)

            def __init__(self, ptree):
                Experiment.__init__(self)
        dummy = DummyExperiment(PropertyTree())
        # produce dummy data for the experiment
        # here just a circle on the complex plane
        n = 10
        f = ones(n, dtype=float)
        Z = ones(n, dtype=complex)
        for i in range(n):
            f[i] = 10**(i / (n - 1))
            Z[i] = cos(2 * pi * i / (n - 1)) + 1j * sin(2 * pi * i / (n - 1))
        dummy._data['frequency'] = f
        dummy._data['impedance'] = Z
        # need a supercapacitor here to make sure method inspect() is kept in
        # sync with the EC-Lab headers
        ptree = PropertyTree()
        ptree.parse_info('super_capacitor.info')
        super_capacitor = EnergyStorageDevice(ptree)
        dummy._extra_data = super_capacitor.inspect()

        # export the data to ECLab format
        eclab = ECLabAsciiFile('untitled.mpt')
        eclab.update(dummy)

        # check that all lines end up with Windows-style line break '/r/n'
        # file need to be open in byte mode or the line ending will be
        # converted to '\n'...
        # also check that the number of lines in the headers has been computed
        # correctly and that the last one contains the column headers
        with open('untitled.mpt', mode='rb') as fin:
            lines = fin.readlines()
            for line in lines:
                self.assertNotEqual(line.find(b'\r\n'), -1)
                self.assertNotEqual(line.find(b'\r\n'), len(line) - 4)
            header_lines = int(lines[1].split(
                b':')[1].lstrip(b'').rstrip(b'\r\n'))
            self.assertEqual(
                header_lines,
                len(eclab._unformated_headers)
            )
            self.assertEqual(lines[header_lines - 1].find(b'freq/Hz'), 0)

        # check Nyquist plot does not throw
        nyquist = NyquistPlot('nyquist.png')
        nyquist.update(dummy)

        # check Bode plot
        # TODO: BodePlot is not implemented yet
#        bode = BodePlot('bode.png')
#        bode.update(dummy)


if __name__ == '__main__':
    unittest.main()
