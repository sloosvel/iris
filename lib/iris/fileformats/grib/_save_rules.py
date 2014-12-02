# (C) British Crown Copyright 2010 - 2014, Met Office
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
"""
Grib save implementation.

This module replaces the deprecated :mod:`iris.fileformats.grib_save_rules'.
It is a private module with no public API.
It is invoked from :meth:`iris.fileformats.grib.save_grib2`.

"""

from __future__ import (absolute_import, division, print_function)

import warnings

import gribapi
import numpy as np
import numpy.ma as ma

import iris
import iris.exceptions
import iris.unit
from iris.fileformats.rules import is_regular, regular_step
from iris.fileformats.grib import grib_phenom_translation as gptx


###############################################################################
#
# Constants
#
###############################################################################

# Reference Flag Table 3.3
_RESOLUTION_AND_COMPONENTS_GRID_WINDS_BIT = 3  # NB "bit5", from MSB=1.

# Reference Regulation 92.1.6
_DEFAULT_DEGREES_UNITS = 1.0e-6


###############################################################################
#
# Identification Section 1
#
###############################################################################

def centre(cube, grib):
    # TODO: read centre from cube
    gribapi.grib_set_long(grib, "centre", 74)  # UKMO
    gribapi.grib_set_long(grib, "subCentre", 0)  # exeter is not in the spec


def reference_time(cube, grib):
    # Set the reference time.
    # (analysis, forecast start, verify time, obs time, etc)
    try:
        fp_coord = cube.coord("forecast_period")
    except iris.exceptions.CoordinateNotFoundError:
        fp_coord = None

    if fp_coord is not None:
        rt, rt_meaning, _, _ = _non_missing_forecast_period(cube)
    else:
        rt, rt_meaning, _, _ = _missing_forecast_period(cube)

    gribapi.grib_set_long(grib, "significanceOfReferenceTime", rt_meaning)
    gribapi.grib_set_long(
        grib, "dataDate", "%04d%02d%02d" % (rt.year, rt.month, rt.day))
    gribapi.grib_set_long(
        grib, "dataTime", "%02d%02d" % (rt.hour, rt.minute))

    # TODO: Set the calendar, when we find out what happened to the proposal!
    # http://tinyurl.com/oefqgv6
    # I was sure it was approved for pre-operational use but it's not there.


def identification(cube, grib):
    centre(cube, grib)
    reference_time(cube, grib)

    # operational product, operational test, research product, etc
    # (missing for now)
    gribapi.grib_set_long(grib, "productionStatusOfProcessedData", 255)
    # analysis, forecast, processed satellite, processed radar,
    # (analysis and forecast products for now)
    gribapi.grib_set_long(grib, "typeOfProcessedData", 2)


###############################################################################
#
# Grid Definition Section 3
#
###############################################################################

def shape_of_the_earth(cube, grib):

    # assume latlon
    cs = cube.coord(dimensions=[0]).coord_system

    # Turn them all missing to start with (255 for byte, -1 for long)
    gribapi.grib_set_long(grib, "scaleFactorOfRadiusOfSphericalEarth", 255)
    gribapi.grib_set_long(grib, "scaledValueOfRadiusOfSphericalEarth", -1)
    gribapi.grib_set_long(grib, "scaleFactorOfEarthMajorAxis", 255)
    gribapi.grib_set_long(grib, "scaledValueOfEarthMajorAxis", -1)
    gribapi.grib_set_long(grib, "scaleFactorOfEarthMinorAxis", 255)
    gribapi.grib_set_long(grib, "scaledValueOfEarthMinorAxis", -1)

    ellipsoid = cs
    if isinstance(cs, iris.coord_systems.RotatedGeogCS):
        ellipsoid = cs.ellipsoid

    if ellipsoid.inverse_flattening == 0.0:
        gribapi.grib_set_long(grib, "shapeOfTheEarth", 1)
        gribapi.grib_set_long(grib, "scaleFactorOfRadiusOfSphericalEarth", 0)
        gribapi.grib_set_long(grib, "scaledValueOfRadiusOfSphericalEarth",
                              ellipsoid.semi_major_axis)
    else:
        gribapi.grib_set_long(grib, "shapeOfTheEarth", 7)
        gribapi.grib_set_long(grib, "scaleFactorOfEarthMajorAxis", 0)
        gribapi.grib_set_long(grib, "scaledValueOfEarthMajorAxis",
                              ellipsoid.semi_major_axis)
        gribapi.grib_set_long(grib, "scaleFactorOfEarthMinorAxis", 0)
        gribapi.grib_set_long(grib, "scaledValueOfEarthMinorAxis",
                              ellipsoid.semi_minor_axis)


def grid_dims(x_coord, y_coord, grib):
    gribapi.grib_set_long(grib, "Ni", x_coord.shape[0])
    gribapi.grib_set_long(grib, "Nj", y_coord.shape[0])


def latlon_first_last(x_coord, y_coord, grib):
    if x_coord.has_bounds() or y_coord.has_bounds():
        warnings.warn("Ignoring xy bounds")

# XXX Pending #1125
#    gribapi.grib_set_double(grib, "latitudeOfFirstGridPointInDegrees",
#                            float(y_coord.points[0]))
#    gribapi.grib_set_double(grib, "latitudeOfLastGridPointInDegrees",
#                            float(y_coord.points[-1]))
#    gribapi.grib_set_double(grib, "longitudeOfFirstGridPointInDegrees",
#                            float(x_coord.points[0]))
#    gribapi.grib_set_double(grib, "longitudeOfLastGridPointInDegrees",
#                            float(x_coord.points[-1]))
# WORKAROUND
    gribapi.grib_set_long(grib, "latitudeOfFirstGridPoint",
                          int(y_coord.points[0]*1000000))
    gribapi.grib_set_long(grib, "latitudeOfLastGridPoint",
                          int(y_coord.points[-1]*1000000))
    gribapi.grib_set_long(grib, "longitudeOfFirstGridPoint",
                          int((x_coord.points[0] % 360)*1000000))
    gribapi.grib_set_long(grib, "longitudeOfLastGridPoint",
                          int((x_coord.points[-1] % 360)*1000000))


def dx_dy(x_coord, y_coord, grib):
    x_step = regular_step(x_coord)
    y_step = regular_step(y_coord)
    # TODO: THIS USED BE "Dx" and "Dy"!!! DID THE API CHANGE AGAIN???
    gribapi.grib_set_double(grib, "DxInDegrees", float(abs(x_step)))
    gribapi.grib_set_double(grib, "DyInDegrees", float(abs(y_step)))


def scanning_mode_flags(x_coord, y_coord, grib):
    gribapi.grib_set_long(grib, "iScansPositively",
                          int(x_coord.points[1] - x_coord.points[0] > 0))
    gribapi.grib_set_long(grib, "jScansPositively",
                          int(y_coord.points[1] - y_coord.points[0] > 0))


def latlon_grid_common(cube, grib):
    # Grib encoding of the sequences of X and Y points.
    y_coord = cube.coord(dimensions=[0])
    x_coord = cube.coord(dimensions=[1])
    shape_of_the_earth(cube, grib)
    grid_dims(x_coord, y_coord, grib)
    scanning_mode_flags(x_coord, y_coord, grib)


def latlon_points_regular(cube, grib):
    y_coord = cube.coord(dimensions=[0])
    x_coord = cube.coord(dimensions=[1])
    latlon_first_last(x_coord, y_coord, grib)
    dx_dy(x_coord, y_coord, grib)


def latlon_points_irregular(cube, grib):
    y_coord = cube.coord(dimensions=[0])
    x_coord = cube.coord(dimensions=[1])

    # Distinguish between true-north and grid-oriented vectors.
    is_grid_wind = cube.name() in ('x_wind', 'y_wind', 'grid_eastward_wind',
                                   'grid_northward_wind')
    # Encode in bit "5" of 'resolutionAndComponentFlags' (other bits unused).
    component_flags = 0
    if is_grid_wind:
        component_flags |= 2 ** _RESOLUTION_AND_COMPONENTS_GRID_WINDS_BIT
    gribapi.grib_set(grib, 'resolutionAndComponentFlags', component_flags)

    # Record the  X and Y coordinate values.
    # NOTE: there is currently a bug in the gribapi which means that the size
    # of the longitudes array does not equal 'Nj', as it should.
    # See : https://software.ecmwf.int/issues/browse/SUP-1096
    # So, this only works at present if the x and y dimensions are **equal**.
    lon_values = x_coord.points / _DEFAULT_DEGREES_UNITS
    lat_values = y_coord.points / _DEFAULT_DEGREES_UNITS
    gribapi.grib_set_array(grib, 'longitudes',
                           np.array(np.round(lon_values), dtype=np.int64))
    gribapi.grib_set_array(grib, 'latitudes',
                           np.array(np.round(lat_values), dtype=np.int64))


def rotated_pole(cube, grib):
    # Grib encoding of a rotated pole coordinate system.
    cs = cube.coord(dimensions=[0]).coord_system

    if cs.north_pole_grid_longitude != 0.0:
        raise iris.exceptions.TranslationError(
            'Grib save does not yet support Rotated-pole coordinates with '
            'a rotated prime meridian.')
# XXX Pending #1125
#    gribapi.grib_set_double(grib, "latitudeOfSouthernPoleInDegrees",
#                            float(cs.n_pole.latitude))
#    gribapi.grib_set_double(grib, "longitudeOfSouthernPoleInDegrees",
#                            float(cs.n_pole.longitude))
#    gribapi.grib_set_double(grib, "angleOfRotationInDegrees", 0)
# WORKAROUND
    latitude = cs.grid_north_pole_latitude / _DEFAULT_DEGREES_UNITS
    longitude = (((cs.grid_north_pole_longitude + 180) % 360) /
                 _DEFAULT_DEGREES_UNITS)
    gribapi.grib_set(grib, "latitudeOfSouthernPole", - int(round(latitude)))
    gribapi.grib_set(grib, "longitudeOfSouthernPole", int(round(longitude)))
    gribapi.grib_set(grib, "angleOfRotation", 0)


def grid_definition_template_0(cube, grib):
    """
    Set keys within the provided grib message based on
    Grid Definition Template 3.0.

    Template 3.0 is used to represent "latitude/longitude (or equidistant
    cylindrical, or Plate Carree)".
    The coordinates are regularly spaced, true latitudes and longitudes.

    """
    # Constant resolution, aka 'regular' true lat-lon grid.
    gribapi.grib_set_long(grib, "gridDefinitionTemplateNumber", 0)
    latlon_grid_common(cube, grib)
    latlon_points_regular(cube, grib)


def grid_definition_template_1(cube, grib):
    """
    Set keys within the provided grib message based on
    Grid Definition Template 3.1.

    Template 3.1 is used to represent "rotated latitude/longitude (or
    equidistant cylindrical, or Plate Carree)".
    The coordinates are regularly spaced, rotated latitudes and longitudes.

    """
    # Constant resolution, aka 'regular' rotated lat-lon grid.
    gribapi.grib_set_long(grib, "gridDefinitionTemplateNumber", 1)

    # Record details of the rotated coordinate system.
    rotated_pole(cube, grib)

    # Encode the lat/lon points.
    latlon_grid_common(cube, grib)
    latlon_points_regular(cube, grib)


def grid_definition_template_5(cube, grib):
    """
    Set keys within the provided grib message based on
    Grid Definition Template 3.5.

    Template 3.5 is used to represent "variable resolution rotated
    latitude/longitude".
    The coordinates are irregularly spaced, rotated latitudes and longitudes.

    """
    # NOTE: we must set Ni=Nj=1 before establishing the template.
    # Without this, setting "gridDefinitionTemplateNumber" = 5 causes an
    # immediate error.
    # See: https://software.ecmwf.int/issues/browse/SUP-1095
    # This is acceptable, as the subsequent call to 'latlon_grid_common' will
    # set these to the correct horizontal dimensions (by calling 'grid_dims').
    gribapi.grib_set(grib, "Ni", 1)
    gribapi.grib_set(grib, "Nj", 1)
    gribapi.grib_set(grib, "gridDefinitionTemplateNumber", 5)

    # Record details of the rotated coordinate system.
    rotated_pole(cube, grib)
    # Encode the lat/lon points.
    latlon_grid_common(cube, grib)
    latlon_points_irregular(cube, grib)


def grid_definition_section(cube, grib):
    """
    Set keys within the grid definition section of the provided grib message,
    based on the properties of the cube.

    """
    x_coord = cube.coord(dimensions=[1])
    y_coord = cube.coord(dimensions=[0])
    cs = x_coord.coord_system  # N.B. already checked same cs for x and y.
    regular_x_and_y = is_regular(x_coord) and is_regular(y_coord)

    if isinstance(cs, iris.coord_systems.GeogCS):
        if not regular_x_and_y:
            raise iris.exceptions.TranslationError(
                'Saving an irregular latlon grid to GRIB (PDT3.4) is not '
                'yet supported.')

        grid_definition_template_0(cube, grib)

    elif isinstance(cs, iris.coord_systems.RotatedGeogCS):
        # Rotated coordinate system cases.
        # Choose between GDT 3.1 and 3.5 according to coordinate regularity.
        if regular_x_and_y:
            grid_definition_template_1(cube, grib)
        else:
            grid_definition_template_5(cube, grib)

    else:
        raise ValueError('Grib saving is not supported for coordinate system: '
                         '{:s}'.format(cs))


###############################################################################
#
# Product Definition Section 4
#
###############################################################################

def set_discipline_and_parameter(cube, grib):
    # NOTE: for now, can match by *either* standard_name or long_name.
    # This allows workarounds for data with no identified standard_name.
    grib2_info = gptx.cf_phenom_to_grib2_info(cube.standard_name,
                                              cube.long_name)
    if grib2_info is not None:
        gribapi.grib_set_long(grib, "discipline", grib2_info.discipline)
        gribapi.grib_set_long(grib, "parameterCategory", grib2_info.category)
        gribapi.grib_set_long(grib, "parameterNumber", grib2_info.number)
    else:
        gribapi.grib_set_long(grib, "discipline", 255)
        gribapi.grib_set_long(grib, "parameterCategory", 255)
        gribapi.grib_set_long(grib, "parameterNumber", 255)
        warnings.warn('Unable to determine Grib2 parameter code for cube.\n'
                      'discipline, parameterCategory and parameterNumber '
                      'have been set to "missing".')


def _non_missing_forecast_period(cube):
    # Calculate "model start time" to use as the reference time.
    fp_coord = cube.coord("forecast_period")

    # Convert fp and t to hours so we can subtract to calculate R.
    cf_fp_hrs = fp_coord.units.convert(fp_coord.points[0], 'hours')
    t_coord = cube.coord("time").copy()
    hours_since = iris.unit.Unit("hours since epoch",
                                 calendar=t_coord.units.calendar)
    t_coord.convert_units(hours_since)

    rt_num = t_coord.points[0] - cf_fp_hrs
    rt = hours_since.num2date(rt_num)
    rt_meaning = 1  # "start of forecast"

    # Forecast period
    if fp_coord.units == iris.unit.Unit("hours"):
        grib_time_code = 1
    elif fp_coord.units == iris.unit.Unit("minutes"):
        grib_time_code = 0
    elif fp_coord.units == iris.unit.Unit("seconds"):
        grib_time_code = 13
    else:
        raise iris.exceptions.TranslationError(
            "Unexpected units for 'forecast_period' : %s" % fp_coord.units)

    if not t_coord.has_bounds():
        fp = fp_coord.points[0]
    else:
        if not fp_coord.has_bounds():
            raise iris.exceptions.TranslationError(
                "bounds on 'time' coordinate requires bounds on"
                " 'forecast_period'.")
        fp = fp_coord.bounds[0][0]

    if fp - int(fp):
        warnings.warn("forecast_period encoding problem: "
                      "scaling required.")
    fp = int(fp)

    # Turn negative forecast times into grib negative numbers?
    from iris.fileformats.grib import hindcast_workaround
    if hindcast_workaround and fp < 0:
        msg = "Encoding negative forecast period from {} to ".format(fp)
        fp = 2**31 + abs(fp)
        msg += "{}".format(np.int32(fp))
        warnings.warn(msg)

    return rt, rt_meaning, fp, grib_time_code


def _missing_forecast_period(cube):
    # We have no way of knowing the CF forecast reference time.
    # Set GRIB reference time to "verifying time of forecast",
    # and the forecast period to 0h.
    warnings.warn('No CF forecast_period. Setting reference time to mean '
                  '"verifying time of forecast", "forecast time" = 0h')

    t_coord = cube.coord("time")
    t = t_coord.bounds[0, 0] if t_coord.has_bounds() else t_coord.points[0]
    rt = t_coord.units.num2date(t)
    rt_meaning = 2  # "verification time of forecast"

    fp = 0
    fp_meaning = 1  # hours

    return rt, rt_meaning, fp, fp_meaning


def set_forecast_time(cube, grib):
    """Grib encoding of forecast_period."""
    try:
        fp_coord = cube.coord("forecast_period")
    except iris.exceptions.CoordinateNotFoundError:
        fp_coord = None

    if fp_coord is not None:
        _, _, fp, grib_time_code = _non_missing_forecast_period(cube)
    else:
        _, _, fp, grib_time_code = _missing_forecast_period(cube)

    gribapi.grib_set_long(grib, "indicatorOfUnitOfTimeRange", grib_time_code)
    gribapi.grib_set_long(grib, "forecastTime", fp)


def set_fixed_surfaces(cube, grib):

    # Look for something we can export
    v_coord = grib_v_code = output_unit = None

    # pressure
    if cube.coords("air_pressure") or cube.coords("pressure"):
        grib_v_code = 100
        output_unit = iris.unit.Unit("Pa")
        v_coord = (cube.coords("air_pressure") or cube.coords("pressure"))[0]

    # altitude
    elif cube.coords("altitude"):
        grib_v_code = 102
        output_unit = iris.unit.Unit("m")
        v_coord = cube.coord("altitude")

    # height
    elif cube.coords("height"):
        grib_v_code = 103
        output_unit = iris.unit.Unit("m")
        v_coord = cube.coord("height")

    # unknown / absent
    else:
        # check for *ANY* height coords at all...
        v_coords = cube.coords(axis='z')
        if v_coords:
            # There are vertical coordinate(s), but we don't understand them...
            v_coords_str = ' ,'.join(["'{}'".format(c.name())
                                      for c in v_coords])
            raise iris.exceptions.TranslationError(
                'The vertical-axis coordinate(s) ({}) '
                'are not recognised or handled.'.format(v_coords_str))

    # What did we find?
    if v_coord is None:
        # No vertical coordinate: record as 'surface' level (levelType=1).
        # NOTE: may *not* be truly correct, but seems to be common practice.
        # Still under investigation :
        # See https://github.com/SciTools/iris/issues/519
        gribapi.grib_set_long(grib, "typeOfFirstFixedSurface", 1)
        gribapi.grib_set_long(grib, "scaleFactorOfFirstFixedSurface", 0)
        gribapi.grib_set_long(grib, "scaledValueOfFirstFixedSurface", 0)
        # Set secondary surface = 'missing'.
        gribapi.grib_set_long(grib, "typeOfSecondFixedSurface", -1)
        gribapi.grib_set_long(grib, "scaleFactorOfSecondFixedSurface", 255)
        gribapi.grib_set_long(grib, "scaledValueOfSecondFixedSurface", -1)
    elif not v_coord.has_bounds():
        # No second surface
        output_v = v_coord.units.convert(v_coord.points[0], output_unit)
        if output_v - abs(output_v):
            warnings.warn("Vertical level encoding problem: scaling required.")
        output_v = int(output_v)

        gribapi.grib_set_long(grib, "typeOfFirstFixedSurface", grib_v_code)
        gribapi.grib_set_long(grib, "scaleFactorOfFirstFixedSurface", 0)
        gribapi.grib_set_long(grib, "scaledValueOfFirstFixedSurface", output_v)
        gribapi.grib_set_long(grib, "typeOfSecondFixedSurface", -1)
        gribapi.grib_set_long(grib, "scaleFactorOfSecondFixedSurface", 255)
        gribapi.grib_set_long(grib, "scaledValueOfSecondFixedSurface", -1)
    else:
        # bounded : set lower+upper surfaces
        output_v = v_coord.units.convert(v_coord.bounds[0], output_unit)
        if output_v[0] - abs(output_v[0]) or output_v[1] - abs(output_v[1]):
            warnings.warn("Vertical level encoding problem: scaling required.")
        gribapi.grib_set_long(grib, "typeOfFirstFixedSurface", grib_v_code)
        gribapi.grib_set_long(grib, "typeOfSecondFixedSurface", grib_v_code)
        gribapi.grib_set_long(grib, "scaleFactorOfFirstFixedSurface", 0)
        gribapi.grib_set_long(grib, "scaleFactorOfSecondFixedSurface", 0)
        gribapi.grib_set_long(grib, "scaledValueOfFirstFixedSurface",
                              int(output_v[0]))
        gribapi.grib_set_long(grib, "scaledValueOfSecondFixedSurface",
                              int(output_v[1]))


def type_of_statistical_processing(cube, grib, coord):
    """Search for processing over the given coord."""
    # if the last cell method applies only to the given coord...
    cell_method = cube.cell_methods[-1]
    coord_names = cell_method.coord_names
    if len(coord_names) != 1:
        raise ValueError('There are multiple coord names referenced by '
                         'the primary cell method: {!r}. Multiple coordinate '
                         'names are not supported.'.format(coord_names))
    if coord_names[0] != coord.name():
        raise ValueError('The coord name referenced by the primary cell method'
                         ', {!r},  is not the expected coord name {!r}.'
                         ''.format(coord_names[0], coord.name()))
    stat_codes = {'mean': 0, 'sum': 1, 'maximum': 2, 'minimum': 3,
                  'standard_deviation': 6}
    # 255 is the code in template 4.8 for 'unknown' statistical method
    stat_code = stat_codes.get(cell_method.method, 255)
    gribapi.grib_set_long(grib, "typeOfStatisticalProcessing", stat_code)


def time_processing_period(cube, grib):
    """
    For template 4.8 (time mean, time max, etc).

    The time range is taken from the 'time' coordinate bounds.
    If the cell-method coordinate is not 'time' itself, the type of statistic
    will not be derived and the save process will be aborted.

    """
    # We could probably split this function up a bit

    # Can safely assume bounded pt.
    pt_coord = cube.coord("time")
    end = iris.unit.num2date(pt_coord.bounds[0, 1], pt_coord.units.name,
                             pt_coord.units.calendar)

    gribapi.grib_set_long(grib, "yearOfEndOfOverallTimeInterval", end.year)
    gribapi.grib_set_long(grib, "monthOfEndOfOverallTimeInterval", end.month)
    gribapi.grib_set_long(grib, "dayOfEndOfOverallTimeInterval", end.day)
    gribapi.grib_set_long(grib, "hourOfEndOfOverallTimeInterval", end.hour)
    gribapi.grib_set_long(grib, "minuteOfEndOfOverallTimeInterval", end.minute)
    gribapi.grib_set_long(grib, "secondOfEndOfOverallTimeInterval", end.second)

    gribapi.grib_set_long(grib, "numberOfTimeRange", 1)
    gribapi.grib_set_long(grib, "numberOfMissingInStatisticalProcess", 0)

    type_of_statistical_processing(cube, grib, pt_coord)

    # Type of time increment, e.g incrementing fp, incrementing ref
    # time, etc. (code table 4.11)
    gribapi.grib_set_long(grib, "typeOfTimeIncrement", 255)
    # time unit for period over which statistical processing is done (hours)
    gribapi.grib_set_long(grib, "indicatorOfUnitForTimeRange", 1)
    # period over which statistical processing is done
    gribapi.grib_set_long(grib, "lengthOfTimeRange",
                          float(pt_coord.bounds[0, 1] - pt_coord.bounds[0, 0]))
    # time unit between successive source fields (not setting this at present)
    gribapi.grib_set_long(grib, "indicatorOfUnitForTimeIncrement", 255)
    # between successive source fields (just set to 0 for now)
    gribapi.grib_set_long(grib, "timeIncrement", 0)


def _cube_is_time_statistic(cube):
    """
    Test whether we can identify this cube as a statistic over time.

    At present, accept anything whose latest cell method operates over a single
    coordinate that "looks like" a time factor (i.e. some specific names).
    In particular, we recognise the coordinate names defined in
    :py:mod:`iris.coord_categorisation`.

    """
    # The *only* relevant information is in cell_methods, as coordinates or
    # dimensions of aggregation may no longer exist.  So it's not possible to
    # be definitive, but we handle *some* useful cases.
    # In other cases just say "no", which is safe even when not ideal.

    # Identify a single coordinate from the latest cell_method.
    if not cube.cell_methods:
        return False
    latest_coordnames = cube.cell_methods[-1].coord_names
    if len(latest_coordnames) != 1:
        return False
    coord_name = latest_coordnames[0]

    # Define accepted time names, including those from coord_categorisations.
    recognised_time_names = ['time', 'year', 'month', 'day', 'weekday',
                             'season']

    # Accept it if the name is recognised.
    # Currently does *not* recognise related names like 'month_number' or
    # 'years', as that seems potentially unsafe.
    return coord_name in recognised_time_names


def product_definition_template_common(cube, grib):
    """
    Set keys within the provided grib message that are common across
    all of the supported product definition templates.

    """
    set_discipline_and_parameter(cube, grib)

    # Various missing values.
    gribapi.grib_set_long(grib, "typeOfGeneratingProcess", 255)
    gribapi.grib_set_long(grib, "backgroundProcess", 255)
    gribapi.grib_set_long(grib, "generatingProcessIdentifier", 255)

    # Generic time handling.
    set_forecast_time(cube, grib)

    # Handle vertical coords.
    set_fixed_surfaces(cube, grib)


def product_definition_template_0(cube, grib):
    """
    Set keys within the provided grib message based on Product
    Definition Template 4.0.

    Template 4.0 is used to represent an analysis or forecast at
    a horizontal level at a point in time.

    """
    gribapi.grib_set_long(grib, "productDefinitionTemplateNumber", 0)
    product_definition_template_common(cube, grib)


def product_definition_template_8(cube, grib):
    """
    Set keys within the provided grib message based on Product
    Definition Template 4.8.

    Template 4.8 is used to represent an aggregation over a time
    interval.

    """
    gribapi.grib_set_long(grib, "productDefinitionTemplateNumber", 8)
    product_definition_template_common(cube, grib)
    try:
        time_processing_period(cube, grib)
    except ValueError as e:
        raise ValueError('Saving to GRIB2 failed: the cube is not suitable'
                         ' for saving as a time processed statistic GRIB'
                         ' message. {}'.format(e))


def product_definition_section(cube, grib):
    """
    Set keys within the product definition section of the provided
    grib message based on the properties of the cube.

    """
    if not cube.coord("time").has_bounds():
        # forecast (template 4.0)
        product_definition_template_0(cube, grib)
    elif _cube_is_time_statistic(cube):
        # time processed (template 4.8)
        product_definition_template_8(cube, grib)
    else:
        # Don't know how to handle this kind of data
        msg = 'A suitable product template could not be deduced'
        raise iris.exceptions.TranslationError(msg)


###############################################################################
#
# Data Representation Section 5
#
###############################################################################

def data_section(cube, grib):
    # Masked data?
    if isinstance(cube.data, ma.core.MaskedArray):
        # What missing value shall we use?
        if not np.isnan(cube.data.fill_value):
            # Use the data's fill value.
            fill_value = float(cube.data.fill_value)
        else:
            # We can't use the data's fill value if it's NaN,
            # the GRIB API doesn't like it.
            # Calculate an MDI outside the data range.
            min, max = cube.data.min(), cube.data.max()
            fill_value = min - (max - min) * 0.1
        # Prepare the unmaksed data array, using fill_value as the MDI.
        data = cube.data.filled(fill_value)
    else:
        fill_value = None
        data = cube.data

    # units scaling
    grib2_info = gptx.cf_phenom_to_grib2_info(cube.standard_name,
                                              cube.long_name)
    if grib2_info is None:
        # for now, just allow this
        warnings.warn('Unable to determine Grib2 parameter code for cube.\n'
                      'Message data may not be correctly scaled.')
    else:
        if cube.units != grib2_info.units:
            data = cube.units.convert(data, grib2_info.units)
            if fill_value is not None:
                fill_value = cube.units.convert(fill_value, grib2_info.units)

    if fill_value is None:
        # Disable missing values in the grib message.
        gribapi.grib_set(grib, "bitmapPresent", 0)
    else:
        # Enable missing values in the grib message.
        gribapi.grib_set(grib, "bitmapPresent", 1)
        gribapi.grib_set_double(grib, "missingValue", fill_value)
    gribapi.grib_set_double_array(grib, "values", data.flatten())

    # todo: check packing accuracy?
#    print("packingError", gribapi.getb_get_double(grib, "packingError"))


###############################################################################

def gribbability_check(cube):
    "We always need the following things for grib saving."

    # GeogCS exists?
    cs0 = cube.coord(dimensions=[0]).coord_system
    cs1 = cube.coord(dimensions=[1]).coord_system
    if cs0 is None or cs1 is None:
        raise iris.exceptions.TranslationError("CoordSystem not present")
    if cs0 != cs1:
        raise iris.exceptions.TranslationError("Inconsistent CoordSystems")

    # Time period exists?
    if not cube.coords("time"):
        raise iris.exceptions.TranslationError("time coord not found")


def run(cube, grib):
    """
    Set the keys of the grib message based on the contents of the cube.

    Args:

    * cube:
        An instance of :class:`iris.cube.Cube`.

    * grib_message_id:
        ID of a grib message in memory. This is typically the return value of
        :func:`gribapi.grib_new_from_samples`.

    """
    gribbability_check(cube)

    # Section 1 - Identification Section.
    identification(cube, grib)

    # Section 3 - Grid Definition Section (Grid Definition Template)
    grid_definition_section(cube, grib)

    # Section 4 - Product Definition Section (Product Definition Template)
    product_definition_section(cube, grib)

    # Section 5 - Data Representation Section (Data Representation Template)
    data_section(cube, grib)
