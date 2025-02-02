#!/usr/bin/env python3
############################################################
# Program is part of MiNoPy                                #
# Author:  Sara Mirzaee                                    #
############################################################
import os
import glob
import warnings
import shutil
import sys
import datetime
from minopy.defaults import auto_path
from mintpy.objects import (geometryDatasetNames,
                            geometry,
                            sensor)
from minopy.objects.slcStack import (slcDatasetNames,
                                     slcStack,
                                     slcStackDict,
                                     slcDict)
from minopy.objects.geometryStack import geometryDict
from mintpy.utils import readfile, ptime, utils as ut
import mintpy.load_data as mld
from minopy.objects.utils import check_template_auto_value
from minopy.objects.utils import read_attribute, coord_rev, print_write_setting
from minopy.objects.arg_parser import MinoPyParser

#################################################################
datasetName2templateKey = {'slc': 'minopy.load.slcFile',
                           'unwrapPhase': 'minopy.load.unwFile',
                           'coherence': 'minopy.load.corFile',
                           'connectComponent': 'minopy.load.connCompFile',
                           'wrapPhase': 'minopy.load.intFile',
                           'iono': 'minopy.load.ionoFile',
                           'height': 'minopy.load.demFile',
                           'latitude': 'minopy.load.lookupYFile',
                           'longitude': 'minopy.load.lookupXFile',
                           'azimuthCoord': 'minopy.load.lookupYFile',
                           'rangeCoord': 'minopy.load.lookupXFile',
                           'incidenceAngle': 'minopy.load.incAngleFile',
                           'azimuthAngle': 'minopy.load.azAngleFile',
                           'shadowMask': 'minopy.load.shadowMaskFile',
                           'waterMask': 'minopy.load.waterMaskFile',
                           'bperp': 'minopy.load.bperpFile'
                           }


#################################################################


def main(iargs=None):
    Parser = MinoPyParser(iargs, script='load_slc')
    inps = Parser.parse()

    dateStr = datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d:%H%M%S')

    if not iargs is None:
        msg = os.path.basename(__file__) + ' ' + ' '.join(iargs[:])
        string = dateStr + " * " + msg
        print(string)
    else:
        msg = os.path.basename(__file__) + ' ' + ' '.join(sys.argv[1:-1])
        string = dateStr + " * " + msg
        print(string)

    os.chdir(inps.work_dir)

    # read input options
    iDict = read_inps2dict(inps)
    
    # prepare metadata
    if not inps.no_metadata_check:
        prepare_metadata(iDict)

    # skip data writing for aria as it is included in prep_aria
    if iDict['processor'] == 'aria':
        return

    iDict = read_subset_box(iDict)

    extraDict = mld.get_extra_metadata(iDict)

    # initiate objects
    stackObj = read_inps_dict2slc_stack_dict_object(iDict)
    
    geomRadarObj, geomGeoObj = read_inps_dict2geometry_dict_object(iDict)

    # prepare write
    updateMode, comp, box, boxGeo, xyStep, xyStepGeo = print_write_setting(iDict)

    if any([stackObj, geomRadarObj, geomGeoObj]) and not os.path.isdir(inps.out_dir):
        os.makedirs(inps.out_dir)
        print('create directory: {}'.format(inps.out_dir))

    # write
    if stackObj and update_object(inps.out_file[0], stackObj, box, updateMode=updateMode):
        print('-' * 50)
        stackObj.write2hdf5(outputFile=inps.out_file[0],
                            access_mode='a',
                            box=box,
                            xstep=xyStep[0],
                            ystep=xyStep[1],
                            compression=comp,
                            extra_metadata=extraDict)

    if geomRadarObj and update_object(inps.out_file[1], geomRadarObj, box, updateMode=updateMode):
        print('-' * 50)
        geomRadarObj.write2hdf5(outputFile=inps.out_file[1],
                                access_mode='a',
                                box=box,
                                xstep=xyStep[0],
                                ystep=xyStep[1],
                                compression='lzf',
                                extra_metadata=extraDict)

    if geomGeoObj and update_object(inps.out_file[2], geomGeoObj, boxGeo, updateMode=updateMode):
        print('-' * 50)
        geomGeoObj.write2hdf5(outputFile=inps.out_file[2],
                              access_mode='a',
                              box=boxGeo,
                              xstep=xyStepGeo[0],
                              ystep=xyStepGeo[1],
                              compression='lzf')
    return inps.out_file


#################################################################


def read_inps2dict(inps):
    """Read input Namespace object info into inpsDict"""
    # Read input info into inpsDict
    inpsDict = vars(inps)
    inpsDict['PLATFORM'] = None
    auto_template = os.path.join(os.path.dirname(__file__), 'defaults/minopyApp_auto.cfg')

    # Read template file
    template = {}
    for fname in inps.template_file:
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

    inpsDict['PLATFORM'] = str(sensor.project_name2sensor_name(str(inpsDict['PROJECT_NAME']))[0])
    if inpsDict['PLATFORM']:
        print('SAR platform/sensor : {}'.format(inpsDict['PLATFORM']))
    print('processor: {}'.format(inpsDict['processor']))

    # Here to insert code to check default file path for miami user
    #work_dir = os.path.dirname(os.path.dirname(inpsDict['outfile']))
    if inpsDict.get('autoPath', False):
        print(('check auto path setting for Univ of Miami users'
               ' for processor: {}'.format(inpsDict['processor'])))
        inpsDict = auto_path.get_auto_path(processor=inpsDict['processor'],
                                           work_dir=inps.work_dir,
                                           template=inpsDict)

    reference_dir = os.path.dirname(inpsDict['minopy.load.metaFile'])
    out_reference = inps.work_dir + '/inputs/reference'
    if not os.path.exists(out_reference):
        shutil.copytree(reference_dir, out_reference)

    baseline_dir = os.path.abspath(inpsDict['minopy.load.baselineDir'])
    out_baseline = inps.work_dir + '/inputs/baselines'
    if not os.path.exists(out_baseline):
        shutil.copytree(baseline_dir, out_baseline)

    return inpsDict


#################################################################


def prepare_metadata(inpsDict):
    processor = inpsDict['processor']
    script_name = 'prep_slc_{}.py'.format(processor)
    print('-' * 50)
    print('prepare metadata files for {} products'.format(processor))
    if processor in ['gamma', 'roipac', 'snap']:
        for key in [i for i in inpsDict.keys() if (i.startswith('minopy.load.') and i.endswith('File'))]:
            if len(glob.glob(str(inpsDict[key]))) > 0:
                cmd = '{} {}'.format(script_name, inpsDict[key])
                print(cmd)
                os.system(cmd)

    elif processor == 'isce':

        slc_dir = os.path.dirname(os.path.dirname(inpsDict['minopy.load.slcFile']))
        slc_file = os.path.basename(inpsDict['minopy.load.slcFile'])
        meta_files = sorted(glob.glob(inpsDict['minopy.load.metaFile']))
        if len(meta_files) < 1:
            warnings.warn('No input metadata file found: {}'.format(inpsDict['minopy.load.metaFile']))
        try:
            meta_file = meta_files[0]
            baseline_dir = inpsDict['minopy.load.baselineDir']
            geom_dir = os.path.dirname(inpsDict['minopy.load.demFile'])
            cmd = '{s} -s {i} -f {f} -m {m} -b {b} -g {g}'.format(s=script_name,
                                                                  i=slc_dir,
                                                                  f=slc_file,
                                                                  m=meta_file,
                                                                  b=baseline_dir,
                                                                  g=geom_dir)
            print(cmd)
            os.system(cmd)
        except:
            pass
    return


#################################################################
def read_subset_template2box(template_file):
    """Read minopy.subset.lalo/yx option from template file into box type
    Return None if not specified.
    (Modified from mintpy.subsets)
    """
    tmpl = readfile.read_template(template_file)
    # subset.lalo -> geo_box
    try:
        opts = [i.strip().replace('[','').replace(']','') for i in tmpl['minopy.subset.lalo'].split(',')]
        lat0, lat1 = sorted([float(i.strip()) for i in opts[0].split(':')])
        lon0, lon1 = sorted([float(i.strip()) for i in opts[1].split(':')])
        geo_box = (lon0, lat1, lon1, lat0)
    except:
        geo_box = None

    # subset.yx -> pix_box
    try:
        opts = [i.strip().replace('[','').replace(']','') for i in tmpl['minopy.subset.yx'].split(',')]
        y0, y1 = sorted([int(i.strip()) for i in opts[0].split(':')])
        x0, x1 = sorted([int(i.strip()) for i in opts[1].split(':')])
        pix_box = (x0, y0, x1, y1)
    except:
        pix_box = None

    return pix_box, geo_box


def read_subset_box(inpsDict):
    # Read subset info from template
    inpsDict['box'] = None
    inpsDict['box4geo_lut'] = None

    pix_box, geo_box = read_subset_template2box(inpsDict['template_file'][0])

    # Grab required info to read input geo_box into pix_box

    try:
        lookupFile = [glob.glob(str(inpsDict['minopy.load.lookupYFile'] + '.xml'))[0],
                      glob.glob(str(inpsDict['minopy.load.lookupXFile'] + '.xml'))[0]]
        lookupFile = [x.split('.xml')[0] for x in lookupFile]
    except:
        lookupFile = None

    try:

        pathKey = [i for i in datasetName2templateKey.values()
                   if i in inpsDict.keys()][0]

        file = glob.glob(str(inpsDict[pathKey] + '.xml'))[0]
        atr = read_attribute(file.split('.xml')[0], metafile_ext='.rsc')
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
            fnames = ut.get_file_list(inpsDict['minopy.load.slcFile'])
            pix_box = mld.update_box4files_with_inconsistent_size(fnames)

        #if not pix_box:
        #    return inpsDict

    # geo_box --> pix_box
    coord = coord_rev(atr, lookup_file=lookupFile)
    if geo_box is not None:
        pix_box = coord.bbox_geo2radar(geo_box)
        pix_box = coord.check_box_within_data_coverage(pix_box)
        print('input bounding box of interest in lalo: {}'.format(geo_box))
    print('box to read for datasets in y/x: {}'.format(pix_box))

    # Get box for geocoded lookup table (for gamma/roipac)
    box4geo_lut = None
    if lookupFile is not None:
        atrLut = read_attribute(lookupFile[0], metafile_ext='.xml')
        if not geocoded and 'Y_FIRST' in atrLut.keys():
            geo_box = coord.bbox_radar2geo(pix_box)
            box4geo_lut = ut.coordinate(atrLut).bbox_geo2radar(geo_box)
            print('box to read for geocoded lookup file in y/x: {}'.format(box4geo_lut))

    if pix_box in [None, 'None'] and 'WIDTH' in atr:
        pix_box = (0, 0, int(atr['WIDTH']), int(atr['LENGTH']))

    for key in atr:
        if not key in inpsDict or inpsDict[key] in [None, 'NONE']:
            inpsDict[key] = atr[key]

    inpsDict['box'] = pix_box
    inpsDict['box4geo_lut'] = box4geo_lut
    return inpsDict


#################################################################

def read_inps_dict2slc_stack_dict_object(inpsDict):
    """Read input arguments into dict of slcStackDict object"""
    # inpsDict --> dsPathDict
    print('-' * 50)
    print('searching slcs info')
    print('input data files:')

    maxDigit = max([len(i) for i in list(datasetName2templateKey.keys())])
    dsPathDict = {}
    for dsName in [i for i in slcDatasetNames
                   if i in datasetName2templateKey.keys()]:
        key = datasetName2templateKey[dsName]
        if key in inpsDict.keys():
            files = sorted(glob.glob(str(inpsDict[key] + '.xml')))
            if len(files) > 0:
                dsPathDict[dsName] = files
                print('{:<{width}}: {path}'.format(dsName,
                                                   width=maxDigit,
                                                   path=inpsDict[key]))

    # Check 1: required dataset
    dsName0 = 'slc'
    if dsName0 not in dsPathDict.keys():
        print('WARNING: No reqired {} data files found!'.format(dsName0))
        return None

    # Check 2: data dimension for slc files
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
        # raise Exception(msg)


    if not inpsDict['minopy.load.startDate'] in [None, 'None']:
        start_date = datetime.datetime.strptime(inpsDict['minopy.load.startDate'], '%Y%m%d')
    else:
        start_date = None
    if not inpsDict['minopy.load.endDate'] in [None, 'None']:
        end_date = datetime.datetime.strptime(inpsDict['minopy.load.endDate'], '%Y%m%d')
    else:
        end_date = None

    # dsPathDict --> pairsDict --> stackObj
    dsNameList = list(dsPathDict.keys())
    pairsDict = {}

    for dsPath in dsPathDict[dsName0]:
        dates = ptime.yyyymmdd(read_attribute(dsPath.split('.xml')[0], metafile_ext='.rsc')['DATE'])
        date_val = datetime.datetime.strptime(dates, '%Y%m%d')
        include_date = True
        if not start_date is None and start_date > date_val:
            include_date = False
        if not end_date is None and end_date < date_val:
            include_date = False

        if include_date:
            #####################################
            # A dictionary of data files for a given pair.
            # One pair may have several types of dataset.
            # example slcPathDict = {'slc': /pathToFile/*.slc.full}
            # All path of data file must contain the reference and secondary date, either in file name or folder name.
            slcPathDict = {}
            for i in range(len(dsNameList)):
                dsName = dsNameList[i]
                dsPath1 = dsPathDict[dsName][0]
                if dates in dsPath1:
                    slcPathDict[dsName] = dsPath1
                else:
                    dsPath2 = [i for i in dsPathDict[dsName] if dates in i]
                    if len(dsPath2) > 0:
                        slcPathDict[dsName] = dsPath2[0]
                    else:
                        print('WARNING: {} file missing for image {}'.format(dsName, dates))

            slcObj = slcDict(dates=dates, datasetDict=slcPathDict)
            pairsDict[dates] = slcObj

    if len(pairsDict) > 0:
        stackObj = slcStackDict(pairsDict=pairsDict)
    else:
        stackObj = None
    return stackObj


def skip_files_with_inconsistent_size(dsPathDict, pix_box=None, dsName='slc'):
    """Skip files by removing the file path from the input dsPathDict."""
    atr_list = [read_attribute(fname.split('.xml')[0], metafile_ext='.xml') for fname in dsPathDict[dsName]]
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
        msg = '\n' + '*' * 80
        msg += '\nWARNING: NOT all input unwrapped interferograms have the same row/column number!'
        msg += '\nThe most common size is: ({}, {})'.format(common_length, common_width)
        msg += '\n' + '-' * 30
        msg += '\nThe following dates have different size:'

        dsNames = list(dsPathDict.keys())
        date_list = [atr['DATE'] for atr in atr_list]
        for i in range(len(date_list)):
            if length_list[i] != common_length or width_list[i] != common_width:
                date = date_list[i]
                dates = ptime.yyyymmdd(date)
                # update file list for all datasets
                for dsName in dsNames:
                    fnames = [i for i in dsPathDict[dsName]
                              if all(d[2:8] in i for d in dates)]
                    if len(fnames) > 0:
                        dsPathDict[dsName].remove(fnames[0])
                msg += '\n\t{}\t({}, {})'.format(date, length_list[i], width_list[i])

        msg += '\n' + '-' * 30
        msg += '\nSkip loading the interferograms above.'
        msg += '\nContinue to load the rest interferograms.'
        msg += '\n' + '*' * 80 + '\n'
        print(msg)
    return dsPathDict


def update_object(outFile, inObj, box, updateMode=True):
    """Do not write h5 file if: 1) h5 exists and readable,
                                2) it contains all date12 from slcStackDict,
                                            or all datasets from geometryDict"""
    write_flag = True
    if updateMode and ut.run_or_skip(outFile, check_readable=True) == 'skip':
        if inObj.name == 'slc':
            in_size = inObj.get_size(box=box)[1:]
            in_date_list = inObj.get_date_list()

            outObj = slcStack(outFile)
            out_size = outObj.get_size()[1:]
            # out_date12_list = outObj.get_date12_list(dropIfgram=False)
            out_date_list = outObj.get_date_list()

            if out_size == in_size and set(in_date_list).issubset(set(out_date_list)):
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


def read_inps_dict2geometry_dict_object(inpsDict):
    # eliminate dsName by processor
    if not 'processor' in inpsDict and 'PROCESSOR'in inpsDict:
        inpsDict['processor'] = inpsDict['PROCESSOR']
    if inpsDict['processor'] in ['isce', 'doris']:
        datasetName2templateKey.pop('azimuthCoord')
        datasetName2templateKey.pop('rangeCoord')
    elif inpsDict['processor'] in ['roipac', 'gamma']:
        datasetName2templateKey.pop('latitude')
        datasetName2templateKey.pop('longitude')
    elif inpsDict['processor'] in ['snap']:
        # check again when there is a SNAP product in radar coordiantes
        pass
    else:
        print('Un-recognized InSAR processor: {}'.format(inpsDict['processor']))

    # inpsDict --> dsPathDict
    print('-' * 50)
    print('searching geometry files info')
    print('input data files:')

    maxDigit = max([len(i) for i in list(datasetName2templateKey.keys())])
    dsPathDict = {}
    for dsName in [i for i in geometryDatasetNames
                   if i in datasetName2templateKey.keys()]:
        key = datasetName2templateKey[dsName]
        if key in inpsDict.keys():
            files = sorted(glob.glob(str(inpsDict[key]) + '.xml'))
            files = [item.split('.xml')[0] for item in files]
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
    slcRadarMetadata = None
    slcKey = datasetName2templateKey['slc']
    if slcKey in inpsDict.keys():
        slcFiles = glob.glob(str(inpsDict[slcKey]))
        if len(slcFiles) > 0:
            atr = readfile.read_attribute(slcFiles[0])
            if 'Y_FIRST' not in atr.keys():
                slcRadarMetadata = atr.copy()

    # dsPathDict --> dsGeoPathDict + dsRadarPathDict
    dsNameList = list(dsPathDict.keys())
    dsGeoPathDict = {}
    dsRadarPathDict = {}
    for dsName in dsNameList:
        if dsName == 'bperp':
            atr = readfile.read_attribute(next(iter(dsPathDict[dsName].values())))
        else:
            atr = read_attribute(dsPathDict[dsName].split('.xml')[0], metafile_ext='.xml')
        if 'Y_FIRST' in atr.keys():
            dsGeoPathDict[dsName] = dsPathDict[dsName]
        else:
            dsRadarPathDict[dsName] = dsPathDict[dsName]

    geomRadarObj = None
    geomGeoObj = None

    if len(dsRadarPathDict) > 0:
        geomRadarObj = geometryDict(processor=inpsDict['processor'],
                                    datasetDict=dsRadarPathDict,
                                    extraMetadata=slcRadarMetadata)
    if len(dsGeoPathDict) > 0:
        geomGeoObj = geometryDict(processor=inpsDict['processor'],
                                  datasetDict=dsGeoPathDict,
                                  extraMetadata=None)
    return geomRadarObj, geomGeoObj


#################################################################
if __name__ == '__main__':
    """
    loading a stack of InSAR pairs to and HDF5 file
    """
    main()
