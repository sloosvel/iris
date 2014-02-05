# (C) British Crown Copyright 2013 - 2014, Met Office
#
# This file is part of Iris.
#
# Iris is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Iris is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Iris.  If not, see <http://www.gnu.org/licenses/>.
"""Unit tests for the :data:`iris.analysis.COUNT` aggregator."""

# Import iris.tests first so that some things can be initialised before
# importing anything else.
import iris.tests as tests

import biggus
import numpy.ma as ma

from iris.analysis import COUNT
import iris.cube
from iris.coords import DimCoord
import iris.exceptions


class Test_units_func(tests.IrisTest):
    def test(self):
        self.assertIsNotNone(COUNT.units_func)
        new_units = COUNT.units_func(None)
        self.assertEqual(new_units, 1)


class Test_masked(tests.IrisTest):
    def setUp(self):
        self.cube = iris.cube.Cube(ma.masked_equal([1, 2, 3, 4, 5], 3))
        self.cube.add_dim_coord(DimCoord([6, 7, 8, 9, 10], long_name='foo'), 0)
        self.func = lambda x: x >= 3

    def test_ma(self):
        cube = self.cube.collapsed("foo", COUNT, function=self.func)
        self.assertArrayEqual(cube.data, [2])

    def test_biggus(self):
        self.cube.lazy_data(array=biggus.NumpyArrayAdapter(self.cube.data))
        with self.assertRaises(iris.exceptions.LazyAggregatorError):
            cube = self.cube.collapsed("foo", COUNT, lazy=True)


if __name__ == "__main__":
    tests.main()
