#!/usr/bin/env python3
########################################################################
# Program is part of MiNoPy and a modified version of Mintpy.load_data #
# Author (Modified by): Sara Mirzaee                                   #
########################################################################

import os
import sys
import glob
import argparse
import warnings
from minopy.defaults import auto_path
from mintpy.objects import (geometryDatasetNames,
                            geometry,
                            ifgramDatasetNames,
                            ifgramStack,
                            sensor)
from mintpy.objects.stackDict import (geometryDict,
                                      ifgramStackDict,
                                      ifgramDict)
from mintpy.utils import readfile, ptime, utils as ut
#from mintpy.utils import isce_utils
from minopy.objects.utils import check_template_auto_value
from mintpy import subset
import datetime

#################################################################
datasetName2templateKey = {'unwrapPhase'     : 'minopy.load.unwFile',
                           'coherence'       : 'minopy.load.corFile',
                           'connectComponent': 'minopy.load.connCompFile',
                           'wrapPhase'       : 'minopy.load.intFile',
                           'iono'            : 'minopy.load.ionoFile',
                           'height'          : 'minopy.load.demFile',
                           'latitude'        : 'minopy.load.lookupYFile',
                           'longitude'       : 'minopy.load.lookupXFile',
                           'azimuthCoord'    : 'minopy.load.lookupYFile',
                           'rangeCoord'      : 'minopy.load.lookupXFile',
                           'incidenceAngle'  : 'minopy.load.incAngleFile',
                           'azimuthAngle'    : 'minopy.load.azAngleFile',
                           'shadowMask'      : 'minopy.load.shadowMaskFile',
                           'waterMask'       : 'minopy.load.waterMaskFile',
                           'bperp'           : 'minopy.load.bperpFile'
                           }

DEFAULT_TEMPLATE = """template:
########## 1. Load ifgrams (--load to exit after this step)
{}\n
{}\n
{}\n
{}\n
""".format(auto_path.isceTopsAutoPath,
           auto_path.isceStripmapAutoPath,
           auto_path.roipacAutoPath,
           auto_path.gammaAutoPath)

TEMPLATE = """template:
########## 1. Load interferograms
## auto - automatic path pattern for Univ of Miami file structure
## load_data.py -H to check more details and example inputs.
## compression to save disk usage for ifgramStack.h5 file:
## no   - save   0% disk usage, fast [default]
## lzf  - save ~57% disk usage, relative slow
## gzip - save ~62% disk usage, very slow [not recommend]

minopy.load.processor      = auto  #[isce,snap,gamma,roipac], auto for isceTops
minopy.load.updateMode     = auto  #[yes / no], auto for yes, skip re-loading if HDF5 files are complete
minopy.load.compression    = auto  #[gzip / lzf / no], auto for no.
minopy.load.autoPath       = auto    # [yes, no] auto for no

##---------interferogram datasets:
minopy.load.unwFile        = auto  #[path2unw_file]
minopy.load.corFile        = auto  #[path2cor_file]
minopy.load.connCompFile   = auto  #[path2conn_file], optional
minopy.load.intFile        = auto  #[path2int_file], optional
minopy.load.ionoFile       = auto  #[path2iono_file], optional
"""

EXAMPLE = """example:
  load_ifgram.py -t PichinchaSenDT142.tempalte
  load_ifgram.py -t minopyApp.cfg
  load_ifgram.py -t minopyApp.cfg PichinchaSenDT142.template --project PichinchaSenDT142
  load_ifgram.py -H #Show example input template for ISCE/ROI_PAC/GAMMA products
"""


def create_parser():
    """Create command line parser."""
    parser = argparse.ArgumentParser(description='Saving a stack of Interferograms to an HDF5 file',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     epilog=TEMPLATE+'\n'+EXAMPLE)
    parser.add_argument('-H', dest='print_example_template', action='store_true',
                        help='Print/Show the example template file for loading.')
    parser.add_argument('-t', '--template', type=str, nargs='+', dest='template_file',
                        help='template file with path info.')

    parser.add_argument('--project', type=str, dest='PROJECT_NAME',
                        help='project name of dataset for INSARMAPS Web Viewer')
    parser.add_argument('--processor', type=str, dest='processor',
                        choices={'isce', 'snap', 'gamma', 'roipac', 'doris', 'gmtsar'},
                        help='InSAR processor/software of the file', default='isce')
    parser.add_argument('--enforce', '-f', dest='updateMode', action='store_false',
                        help='Disable the update mode, or skip checking dataset already loaded.')
    parser.add_argument('--compression', choices={'gzip', 'lzf', None}, default=None,
                        help='compress loaded geometry while writing HDF5 file, default: None.')

    parser.add_argument('-o', '--output', type=str, dest='outfile',
                        default='./inputs/ifgramStack.h5',
                        help='output HDF5 file')
    return parser


def cmd_line_parse(iargs=None):
    """Command line parser."""
    parser = create_parser()
    inps = parser.parse_args(args=iargs)

    if inps.template_file:
        pass
    elif inps.print_example_template:
        raise SystemExit(DEFAULT_TEMPLATE)
    else:
        parser.print_usage()
        print(('{}: error: one of the following arguments are required:'
               ' -t/--template, -H'.format(os.path.basename(__file__))))
        print('{} -H to show the example template file'.format(os.path.basename(__file__)))
        sys.exit(1)

    inps.outdir = os.path.dirname(inps.outfile)

    return inps


#################################################################
def read_inps2dict(inps):
    """Read input Namespace object info into inpsDict"""
    # Read input info into inpsDict
    inpsDict = vars(inps)
    inpsDict['PLATFORM'] = None
    auto_template = os.path.join(os.path.dirname(__file__), 'defaults/minopyApp_auto.cfg')

    # Read template file
    template = {}
    for fname in list(inps.template_file):
        temp = readfile.read_template(fname)
        temp = check_template_auto_value(temp, auto_file=auto_template)
        template.update(temp)
    for key, value in template.items():
        inpsDict[key] = value
    if 'processor' in template.keys():
        template['minopy.load.processor'] = template['processor']

    prefix = 'minopy.load.'
    key_list = [i.split(prefix)[1] for i in template.keys() if i.startswith(prefix)]
    for key in key_list:
        value = template[prefix + key]
        if key in ['processor', 'updateMode', 'compression', 'autoPath']:
            inpsDict[key] = template[prefix + key]
        elif key in ['xstep', 'ystep']:
            inpsDict[key] = int(template[prefix + key])
        elif value:
            inpsDict[prefix + key] = template[prefix + key]

    if not 'compression' in inpsDict or inpsDict['compression'] == False:
        inpsDict['compression'] = None

    inpsDict['xstep'] = inpsDict.get('xstep', 1)
    inpsDict['ystep'] = inpsDict.get('ystep', 1)

    # PROJECT_NAME --> PLATFORM
    if not 'PROJECT_NAME' in inpsDict:
        cfile = [i for i in list(inps.template_file) if os.path.basename(i) != 'minopyApp.cfg']
        inpsDict['PROJECT_NAME'] = sensor.project_name2sensor_name(cfile)[1]

    msg = 'SAR platform/sensor : '
    sensor_name = sensor.project_name2sensor_name(str(inpsDict['PROJECT_NAME']))[0]
    if sensor_name:
        msg += str(sensor_name)
        inpsDict['PLATFORM'] = str(sensor_name)
    else:
        msg += 'unknown from project name "{}"'.format(inpsDict['PROJECT_NAME'])
    print(msg)
    
    # Here to insert code to check default file path for miami user
    work_dir = os.path.dirname(os.path.dirname(inpsDict['outfile']))
    if inpsDict.get('autoPath', False):
        print(('check auto path setting for Univ of Miami users'
               ' for processor: {}'.format(inpsDict['processor'])))
        inpsDict = auto_path.get_auto_path(processor=inpsDict['processor'],
                                           work_dir=work_dir,
                                           template=inpsDict)
    return inpsDict


def read_subset_box(inpsDict):
    # Read subset info from template
    inpsDict['box'] = None
    inpsDict['box4geo_lut'] = None
    pix_box, geo_box = subset.read_subset_template2box(inpsDict['template_file'][0])

    # Grab required info to read input geo_box into pix_box
    try:
        lookupFile = [glob.glob(str(inpsDict['minopy.load.lookupYFile']))[0],
                      glob.glob(str(inpsDict['minopy.load.lookupXFile']))[0]]
    except:
        lookupFile = None

    try:
        pathKey = [i for i in datasetName2templateKey.values()
                   if i in inpsDict.keys()][0]
        file = glob.glob(str(inpsDict[pathKey]))[0]
        atr = readfile.read_attribute(file)
    except:
        atr = dict()

    geocoded = None
    if 'Y_FIRST' in atr.keys():
        geocoded = True
    else:
        geocoded = False

    # Check conflict
    if geo_box and not geocoded and lookupFile is None:
        geo_box = None
        print(('WARNING: mintpy.subset.lalo is not supported'
               ' if 1) no lookup file AND'
               '    2) radar/unkonwn coded dataset'))
        print('\tignore it and continue.')

    if not geo_box and not pix_box:
        # adjust for the size inconsistency problem in SNAP geocoded products
        # ONLY IF there is no input subset
        # Use the min bbox if files size are different
        if inpsDict['processor'] == 'snap':
            fnames = ut.get_file_list(inpsDict['minopy.load.unwFile'])
            pix_box = update_box4files_with_inconsistent_size(fnames)

        if not pix_box:
            return inpsDict

    # geo_box --> pix_box
    coord = ut.coordinate(atr, lookup_file=lookupFile)

    if geo_box is not None:
        pix_box = (0, 0, int(atr['width']), int(atr['length']))    # coord.bbox_geo2radar(geo_box)
        pix_box = coord.check_box_within_data_coverage(pix_box)
        print('input bounding box of interest in lalo: {}'.format(geo_box))
    print('box to read for datasets in y/x: {}'.format(pix_box))

    # Get box for geocoded lookup table (for gamma/roipac)
    box4geo_lut = None
    if lookupFile is not None:
        atrLut = readfile.read_attribute(lookupFile[0])
        if not geocoded and 'Y_FIRST' in atrLut.keys():
            geo_box = coord.bbox_radar2geo(pix_box)
            box4geo_lut = ut.coordinate(atrLut).bbox_geo2radar(geo_box)
            print('box to read for geocoded lookup file in y/x: {}'.format(box4geo_lut))

    inpsDict['box'] = pix_box
    inpsDict['box4geo_lut'] = box4geo_lut
    return inpsDict


def update_box4files_with_inconsistent_size(fnames):
    """Check the size (row / column number) of a list of files
    For SNAP geocoded products has one line missing in some interferograms, Andre, 2019-07-16
    Parameters: fnames  : list of path for interferogram files
    Returns:    pix_box : None if all files are in same size
                          (0, 0, min_width, min_length) if not.
    """
    atr_list = [readfile.read_attribute(fname) for fname in fnames]
    length_list = [int(atr['LENGTH']) for atr in atr_list]
    width_list = [int(atr['WIDTH']) for atr in atr_list]
    if any(len(set(i)) for i in [length_list, width_list]):
        min_length = min(length_list)
        min_width = min(width_list)
        pix_box = (0, 0, min_width, min_length)

        # print out warning message
        msg = '\n'+'*'*80
        msg += '\nWARNING: NOT all input unwrapped interferograms have the same row/column number!'
        msg += '\nMinimum size is: ({}, {})'.format(min_length, min_width)
        msg += '\n'+'-'*30
        msg += '\nThe following dates have different size:'

        for i in range(len(fnames)):
            if length_list[i] != min_length or width_list[i] != min_width:
                msg += '\n\t{}\t({}, {})'.format(atr_list[i]['DATE12'], length_list[i], width_list[i])

        msg += '\n'+'-'*30
        msg += '\nAssuming the interferograms above have:'
        msg += '\n\textra line(s) at the bottom OR'
        msg += '\n\textra column(s) at the right'
        msg += '\nContinue to load data using subset of the minimum size.'
        msg += '\n'+'*'*80+'\n'
        print(msg)
    else:
        pix_box = None
    return pix_box


def skip_files_with_inconsistent_size(dsPathDict, pix_box=None, dsName='unwrapPhase'):
    """Skip files by removing the file path from the input dsPathDict."""
    atr_list = [readfile.read_attribute(fname) for fname in dsPathDict[dsName]]
    length_list = [int(atr['LENGTH']) for atr in atr_list]
    width_list = [int(atr['WIDTH']) for atr in atr_list]

    # Check size requirements
    drop_inconsistent_files = False
    if any(len(set(size_list)) > 1 for size_list in [length_list, width_list]):
        if pix_box is None:
            drop_inconsistent_files = True
        else:
            # if input subset is within the min file sizes: do NOT drop
            max_box_width, max_box_length = pix_box[2:4]
            if max_box_length > min(length_list) or max_box_width > min(width_list):
                drop_inconsistent_files = True

    # update dsPathDict
    if drop_inconsistent_files:
        common_length = ut.most_common(length_list)
        common_width = ut.most_common(width_list)

        # print out warning message
        msg = '\n'+'*'*80
        msg += '\nWARNING: NOT all input unwrapped interferograms have the same row/column number!'
        msg += '\nThe most common size is: ({}, {})'.format(common_length, common_width)
        msg += '\n'+'-'*30
        msg += '\nThe following dates have different size:'

        dsNames = list(dsPathDict.keys())
        date12_list = [atr['DATE12'] for atr in atr_list]
        for i in range(len(date12_list)):
            if length_list[i] != common_length or width_list[i] != common_width:
                date12 = date12_list[i]
                dates = ptime.yyyymmdd(date12.split('-'))
                # update file list for all datasets
                for dsName in dsNames:
                    fnames = [i for i in dsPathDict[dsName]
                              if all(d[2:8] in i for d in dates)]
                    if len(fnames) > 0:
                        dsPathDict[dsName].remove(fnames[0])
                msg += '\n\t{}\t({}, {})'.format(date12, length_list[i], width_list[i])

        msg += '\n'+'-'*30
        msg += '\nSkip loading the interferograms above.'
        msg += '\nContinue to load the rest interferograms.'
        msg += '\n'+'*'*80+'\n'
        print(msg)
    return dsPathDict


def read_inps_dict2ifgram_stack_dict_object(inpsDict):
    """Read input arguments into dict of ifgramStackDict object"""
    # inpsDict --> dsPathDict
    print('-'*50)
    print('searching interferometric pairs info')
    print('input data files:')
    maxDigit = max([len(i) for i in list(datasetName2templateKey.keys())])
    dsPathDict = {}
    for dsName in [i for i in ifgramDatasetNames
                   if i in datasetName2templateKey.keys()]:
        key = datasetName2templateKey[dsName]
        if key in inpsDict.keys():
            files = sorted(glob.glob(str(inpsDict[key])))
            if len(files) > 0:
                dsPathDict[dsName] = files
                print('{:<{width}}: {path}'.format(dsName,
                                                   width=maxDigit,
                                                   path=inpsDict[key]))


    # Check 1: required dataset
    dsName0s = ['unwrapPhase']
    dsName0 = [i for i in dsName0s if i in dsPathDict.keys()]
    if len(dsName0) == 0:
        print('WARNING: No reqired {} data files found!'.format(dsName0))
        return None
    else:
        dsName0 = dsName0[0]

    # Check 2: data dimension for unwrapPhase files
    dsPathDict = skip_files_with_inconsistent_size(dsPathDict,
                                                   pix_box=inpsDict['box'],
                                                   dsName=dsName0)

    # Check 3: number of files for all dataset types
    # dsPathDict --> dsNumDict
    dsNumDict = {}
    for key in dsPathDict.keys():
        num_file = len(dsPathDict[key])
        dsNumDict[key] = num_file
        print('number of {:<{width}}: {num}'.format(key, width=maxDigit, num=num_file))

    dsNumList = list(dsNumDict.values())
    if any(i != dsNumList[0] for i in dsNumList):
        msg = 'WARNING: NOT all types of dataset have the same number of files.'
        msg += ' -> skip interferograms with missing files and continue.'
        print(msg)
        #raise Exception(msg)

    # dsPathDict --> pairsDict --> stackObj
    dsNameList = list(dsPathDict.keys())
    pairsDict = {}
    for dsPath in dsPathDict[dsName0]:
        date12 = readfile.read_attribute(dsPath)['DATE12'].replace('_', '-')
        dates = ptime.yyyymmdd(date12.split('-'))

        #####################################
        # A dictionary of data files for a given pair.
        # One pair may have several types of dataset.
        # example ifgramPathDict = {'unwrapPhase': /pathToFile/filt.unw, 'iono':/PathToFile/iono.bil}
        # All path of data file must contain the reference and secondary date, either in file name or folder name.

        ifgramPathDict = {}
        for i in range(len(dsNameList)):
            dsName = dsNameList[i]
            dsPath1 = dsPathDict[dsName][0]

            if all(d[2:8] in dsPath1 for d in dates):
                ifgramPathDict[dsName] = dsPath1

            else:
                dsPath2 = [i for i in dsPathDict[dsName]
                           if all(d[2:8] in i for d in dates)]

                if len(dsPath2) > 0:
                    ifgramPathDict[dsName] = dsPath2[0]
                else:
                    print('WARNING: {} file missing for pair {}'.format(dsName, dates))

        ifgramObj = ifgramDict(datasetDict=ifgramPathDict)

        pairsDict[tuple(dates)] = ifgramObj

    if len(pairsDict) > 0:
        stackObj = ifgramStackDict(pairsDict=pairsDict)
    else:
        stackObj = None
    return stackObj


def read_inps_dict2geometry_dict_object(inpsDict):

    # eliminate dsName by processor
    if inpsDict['processor'] in ['isce', 'doris']:
        datasetName2templateKey.pop('azimuthCoord')
        datasetName2templateKey.pop('rangeCoord')
    elif inpsDict['processor'] in ['roipac', 'gamma']:
        datasetName2templateKey.pop('latitude')
        datasetName2templateKey.pop('longitude')
    elif inpsDict['processor'] in ['snap']:
        #check again when there is a SNAP product in radar coordiantes
        pass
    else:
        print('Un-recognized InSAR processor: {}'.format(inpsDict['processor']))

    # inpsDict --> dsPathDict
    print('-'*50)
    print('searching geometry files info')
    print('input data files:')

    maxDigit = max([len(i) for i in list(datasetName2templateKey.keys())])
    dsPathDict = {}
    for dsName in [i for i in geometryDatasetNames
                   if i in datasetName2templateKey.keys()]:
        key = datasetName2templateKey[dsName]
        if key in inpsDict.keys():
            files = sorted(glob.glob(str(inpsDict[key])))
            if len(files) > 0:
                if dsName == 'bperp':
                    bperpDict = {}
                    for file in files:
                        date = ptime.yyyymmdd(os.path.basename(os.path.dirname(file)))
                        bperpDict[date] = file
                    dsPathDict[dsName] = bperpDict
                    print('{:<{width}}: {path}'.format(dsName,
                                                       width=maxDigit,
                                                       path=inpsDict[key]))
                    print('number of bperp files: {}'.format(len(list(bperpDict.keys()))))
                else:
                    dsPathDict[dsName] = files[0]
                    print('{:<{width}}: {path}'.format(dsName,
                                                       width=maxDigit,
                                                       path=files[0]))

    # Check required dataset
    dsName0 = geometryDatasetNames[0]
    if dsName0 not in dsPathDict.keys():
        print('WARNING: No reqired {} data files found!'.format(dsName0))

    # metadata
    ifgramRadarMetadata = None
    ifgramKey = datasetName2templateKey['unwrapPhase']
    if ifgramKey in inpsDict.keys():
        ifgramFiles = glob.glob(str(inpsDict[ifgramKey]))
        if len(ifgramFiles) > 0:
            atr = readfile.read_attribute(ifgramFiles[0])
            if 'Y_FIRST' not in atr.keys():
                ifgramRadarMetadata = atr.copy()

    # dsPathDict --> dsGeoPathDict + dsRadarPathDict
    dsNameList = list(dsPathDict.keys())
    dsGeoPathDict = {}
    dsRadarPathDict = {}
    for dsName in dsNameList:
        if dsName == 'bperp':
            atr = readfile.read_attribute(next(iter(dsPathDict[dsName].values())))
        else:
            atr = readfile.read_attribute(dsPathDict[dsName])
        if 'Y_FIRST' in atr.keys():
            dsGeoPathDict[dsName] = dsPathDict[dsName]
        else:
            dsRadarPathDict[dsName] = dsPathDict[dsName]

    geomRadarObj = None
    geomGeoObj = None
    if len(dsRadarPathDict) > 0:
        geomRadarObj = geometryDict(processor=inpsDict['processor'],
                                    datasetDict=dsRadarPathDict,
                                    extraMetadata=ifgramRadarMetadata)
    if len(dsGeoPathDict) > 0:
        geomGeoObj = geometryDict(processor=inpsDict['processor'],
                                  datasetDict=dsGeoPathDict,
                                  extraMetadata=None)
    return geomRadarObj, geomGeoObj


def update_object(outFile, inObj, box, updateMode=True):
    """Do not write h5 file if: 1) h5 exists and readable,
                                2) it contains all date12 from ifgramStackDict,
                                            or all datasets from geometryDict"""
    write_flag = True
    if updateMode and ut.run_or_skip(outFile, check_readable=True) == 'skip':
        if inObj.name == 'ifgramStack':
            in_size = inObj.get_size(box=box)[1:]
            in_date12_list = inObj.get_date12_list()

            outObj = ifgramStack(outFile)
            out_size = outObj.get_size()[1:]
            out_date12_list = outObj.get_date12_list(dropIfgram=False)

            if out_size == in_size and set(in_date12_list).issubset(set(out_date12_list)):
                print(('All date12   exists in file {} with same size as required,'
                       ' no need to re-load.'.format(os.path.basename(outFile))))
                write_flag = False

        elif inObj.name == 'geometry':
            outObj = geometry(outFile)
            outObj.open(print_msg=False)
            if (outObj.get_size() == inObj.get_size(box=box)
                    and all(i in outObj.datasetNames for i in inObj.get_dataset_list())):
                print(('All datasets exists in file {} with same size as required,'
                       ' no need to re-load.'.format(os.path.basename(outFile))))
                write_flag = False
    return write_flag


def prepare_metadata(inpsDict):
    processor = inpsDict['processor']
    script_name = 'prep_{}.py'.format(processor)
    print('-'*50)
    print('prepare metadata files for {} products'.format(processor))

    if processor in ['gamma', 'roipac', 'snap']:
        for key in [i for i in inpsDict.keys() if (i.startswith('minopy.load.') and i.endswith('File'))]:
            if len(glob.glob(str(inpsDict[key]))) > 0:
                cmd = '{} {}'.format(script_name, inpsDict[key])
                print(cmd)
                os.system(cmd)

    elif processor == 'isce':
        meta_files = sorted(glob.glob(inpsDict['minopy.load.metaFile']))
        if len(meta_files) < 1:
            warnings.warn('No input metadata file found: {}'.format(inpsDict['minopy.load.metaFile']))
        try:
            # metadata and auxliary data
            meta_file = meta_files[0]
            baseline_dir = inpsDict['minopy.load.baselineDir']
            geom_dir = os.path.dirname(inpsDict['minopy.load.demFile'])
            # observation
            obs_keys = ['minopy.load.unwFile', 'minopy.load.azOffFile']
            obs_keys = [i for i in obs_keys if i in inpsDict.keys()]
            obs_paths = [inpsDict[key] for key in obs_keys if inpsDict[key].lower() != 'auto']
            if len(obs_paths) > 0:
                obs_dir = os.path.dirname(os.path.dirname(obs_paths[0]))
                obs_file = os.path.basename(obs_paths[0])
            else:
                obs_dir = None
                obs_file = None

            # command line
            cmd = '{s} -m {m} -g {g}'.format(s=script_name, m=meta_file, g=geom_dir)
            if baseline_dir:
                cmd += ' -b {b} '.format(b=baseline_dir)
            if obs_dir is not None:
                cmd += ' -d {d} -f {f} '.format(d=obs_dir, f=obs_file)
            print(cmd)
            os.system(cmd)
        except:
            pass
    return


def print_write_setting(inpsDict):
    updateMode = inpsDict['updateMode']
    comp = inpsDict['compression']
    print('-'*50)
    print('updateMode : {}'.format(updateMode))
    print('compression: {}'.format(comp))
    box = inpsDict['box']
    boxGeo = inpsDict['box4geo_lut']
    return updateMode, comp, box, boxGeo


def get_extra_metadata(inpsDict):
    """Extra metadata to be written into stack file"""
    extraDict = {}
    for key in ['PROJECT_NAME', 'PLATFORM']:
        if inpsDict[key]:
            extraDict[key] = inpsDict[key]
    for key in ['SUBSET_XMIN', 'SUBSET_YMIN']:
        if key in inpsDict.keys():
            extraDict[key] = inpsDict[key]
    return extraDict


#################################################################
def main(iargs=None):
    inps = cmd_line_parse(iargs)

    dateStr = datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d:%H%M%S')

    if not iargs is None:
        msg = os.path.basename(__file__) + ' ' + ' '.join(iargs[:])
        string = dateStr + " * " + msg
        print(string)
    else:
        msg = os.path.basename(__file__) + ' ' + ' '.join(sys.argv[1::])
        string = dateStr + " * " + msg
        print(string)

    work_dir = os.path.dirname(inps.outdir)
    #os.chdir(work_dir)

    # read input options
    inpsDict = read_inps2dict(inps)
    prepare_metadata(inpsDict)

    inpsDict = read_subset_box(inpsDict)
    extraDict = get_extra_metadata(inpsDict)

    if not 'PLATFORM' in extraDict:
        slcStack = os.path.join(inps.outdir, 'slcStack.h5')
        atr = readfile.read_attribute(slcStack)
        if 'PLATFORM' in atr:
            extraDict['PLATFORM'] = atr['PLATFORM']

    # initiate objects
    stackObj = read_inps_dict2ifgram_stack_dict_object(inpsDict)

    # prepare wirte
    updateMode, comp, box, boxGeo = print_write_setting(inpsDict)
    box = None
    boxGeo = None
    if stackObj and not os.path.isdir(inps.outdir):
        os.makedirs(inps.outdir)
        print('create directory: {}'.format(inps.outdir))
    # write
    if stackObj and update_object(inps.outfile, stackObj, box, updateMode=updateMode):
        print('-'*50)
        stackObj.write2hdf5(outputFile=inps.outfile,
                            access_mode='w',
                            box=box,
                            compression=comp,
                            extra_metadata=extraDict)

    # check loading result
    load_complete, stack_file, geom_file = ut.check_loaded_dataset(work_dir=work_dir, print_msg=True)[0:3]

    # add custom metadata (optional)
    customTemplate = inps.template_file[0]
    if customTemplate:
        print('updating {}, {} metadata based on custom template file: {}'.format(
            os.path.basename(stack_file),
            os.path.basename(geom_file),
            os.path.basename(customTemplate)))
        # use ut.add_attribute() instead of add_attribute.py because of
        # better control of special metadata, such as SUBSET_X/YMIN
        ut.add_attribute(stack_file, inpsDict)
        ut.add_attribute(geom_file, inpsDict)

    ut.add_attribute(stack_file, extraDict)

    # if not load_complete, plot and raise exception
    if not load_complete:
        # go back to original directory
        print('Go back to directory:', work_dir)
        os.chdir(work_dir)

        # raise error
        msg = 'step load_ifgram: NOT all required dataset found, exit.'
        raise SystemExit(msg)

    return inps.outfile


#################################################################
if __name__ == '__main__':
    """
    loading a stack of InSAR pairs to and HDF5 file
    """
    main()
