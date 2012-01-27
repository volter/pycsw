#!/usr/bin/python
# -*- coding: ISO-8859-15 -*-
# =================================================================
#
# $Id$
#
# Authors: Tom Kralidis <tomkralidis@hotmail.com>
#
# Copyright (c) 2012 Tom Kralidis
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================

from ConfigParser import SafeConfigParser
import getopt
import os
import sys
from glob import glob

from lxml import etree
from server import metadata, repository, util

def setup_db(database, home):
    ''' Setup database tables and indexes '''
    from sqlalchemy import Column, create_engine, Integer, String, MetaData, \
    Table, Text

    print 'Creating database %s' % database
    DB = create_engine(database)

    METADATA = MetaData(DB)

    print 'Creating table spatial_ref_sys'
    SRS = Table('spatial_ref_sys', METADATA,
        Column('srid', Integer, nullable=False, primary_key=True),
        Column('auth_name', String(256)),
        Column('auth_srid', Integer),
        Column('srtext', String(2048))
    )
    SRS.create()

    i = SRS.insert()
    i.execute(srid=4326, auth_name='EPSG', auth_srid=4326, srtext='GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.01745329251994328,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]')

    print 'Creating table geometry_columns'
    GEOM = Table('geometry_columns', METADATA,
        Column('f_table_catalog', String(256), nullable=False),
        Column('f_table_schema', String(256), nullable=False),
        Column('f_table_name', String(256), nullable=False),
        Column('f_geometry_column', String(256), nullable=False),
        Column('geometry_type', Integer),
        Column('coord_dimension', Integer),
        Column('srid', Integer, nullable=False),
        Column('geometry_format', String(5), nullable=False),
    )
    GEOM.create()

    i = GEOM.insert()
    i.execute(f_table_catalog='public', f_table_schema='public',
    f_table_name='records', f_geometry_column='wkt_geometry', 
    geometry_type=3, coord_dimension=2, srid=4326, geometry_format='WKT')

    # abstract metadata information model

    print 'Creating table records'
    RECORDS = Table('records', METADATA,
        # core; nothing happens without these
        Column('identifier', String(256), primary_key=True),
        Column('typename', String(32),
        default='csw:Record', nullable=False, index=True),
        Column('schema', String(256),
        default='http://www.opengis.net/cat/csw/2.0.2', nullable=False,
        index=True),
        Column('mdsource', String(256), default='local', nullable=False,
        index=True),
        Column('insert_date', String(20), nullable=False, index=True),
        Column('xml', Text, nullable=False),
        Column('anytext', Text, nullable=False),
        Column('language', String(32), index=True),
    
        # identification
        Column('type', String(128), index=True),
        Column('title', String(2048), index=True),
        Column('title_alternate', String(2048), index=True),
        Column('abstract', String(2048), index=True),
        Column('keywords', String(2048), index=True),
        Column('keywordstype', String(256), index=True),
        Column('parentidentifier', String(32), index=True),
        Column('relation', String(256), index=True),
        Column('time_begin', String(20), index=True),
        Column('time_end', String(20), index=True),
        Column('topicategory', String(32), index=True),
        Column('resourcelanguage', String(32), index=True),
    
        # attribution
        Column('creator', String(256), index=True),
        Column('publisher', String(256), index=True),
        Column('contributor', String(256), index=True),
        Column('organization', String(256), index=True),
    
        # security
        Column('securityconstraints', String(256), index=True),
        Column('accessconstraints', String(256), index=True),
        Column('otherconstraints', String(256), index=True),
    
        # date
        Column('date', String(20), index=True),
        Column('date_revision', String(20), index=True),
        Column('date_creation', String(20), index=True),
        Column('date_publication', String(20), index=True),
        Column('date_modified', String(20), index=True),
    
        Column('format', String(128), index=True),
        Column('source', String(1024), index=True),
    
        # geospatial
        Column('crs', String(256), index=True),
        Column('geodescode', String(256), index=True),
        Column('denominator', Integer, index=True),
        Column('distancevalue', Integer, index=True),
        Column('distanceuom', String(8), index=True),
        Column('wkt_geometry', Text),
    
        # service
        Column('servicetype', String(32), index=True),
        Column('servicetypeversion', String(32), index=True),
        Column('operation', String(32), index=True),
        Column('couplingtype', String(8), index=True),
        Column('operateson', String(32), index=True),
        Column('operatesonidentifier', String(32), index=True),
        Column('operatesoname', String(32), index=True),
    
        # additional
        Column('degree', String(8), index=True),
        Column('classification', String(32), index=True),
        Column('conditionapplyingtoaccessanduse', String(256), index=True),
        Column('lineage', String(32), index=True),
        Column('responsiblepartyrole', String(32), index=True),
        Column('specificationtitle', String(32), index=True),
        Column('specificationdate', String(20), index=True),
        Column('specificationdatetype', String(20), index=True),
    
        # distribution
        # links: format "name,description,protocol,url^[,,,^[,,,]]"
        Column('links', Text, index=True),
    )
    RECORDS.create()
    
    if DB.name == 'postgresql':  # create plpythonu functions within db
        PYCSW_HOME = home
        CONN = DB.connect()
        FUNCTION_QUERY_SPATIAL = '''
    CREATE OR REPLACE FUNCTION query_spatial(bbox_data_wkt text, bbox_input_wkt text, predicate text, distance text)
    RETURNS text
    AS $$
        import sys
        sys.path.append('%s')
        from server import util
        return util.query_spatial(bbox_data_wkt, bbox_input_wkt, predicate, distance)
        $$ LANGUAGE plpythonu;
    ''' % PYCSW_HOME
        FUNCTION_UPDATE_XPATH = '''
    CREATE OR REPLACE FUNCTION update_xpath(xml text, recprops text)
    RETURNS text
    AS $$
        import sys
        sys.path.append('%s')
        from server import util
        return util.update_xpath(xml, recprops)
        $$ LANGUAGE plpythonu;
    ''' % PYCSW_HOME
        CONN.execute(FUNCTION_QUERY_SPATIAL)
        CONN.execute(FUNCTION_UPDATE_XPATH)

def load_records(database, xml_dirpath):
    ''' Load metadata records from directory of files to database ''' 
    REPO = repository.Repository(database, 'records', {})

    for r in glob(os.path.join(xml_dirpath, '*.xml')):
        print 'Processing file %s' % r
        # read document
        try:
            e = etree.parse(r)
        except Exception, err:
            print 'XML document is not well-formed: %s' % str(err)
            continue

        record = metadata.parse_record(e, REPO)

        for rec in record:
            print 'Inserting %s %s into database %s, table records....' % \
            (rec.typename, rec.identifier, database)

            # TODO: do this as CSW Harvest
            try:
                REPO.insert(rec, 'local', util.get_today_and_now())
                print 'Inserted'
            except Exception, err:
                print 'ERROR: not inserted %s' % err

def export_records(database, xml_dirpath):
    ''' Export metadata records from database to directory of files '''
    REPO = repository.Repository(database, 'records', {})

    print 'Querying database %s, table records....' % database
    RECORDS = REPO.session.query(REPO.dataset)

    print 'Found %d records\n' % RECORDS.count()

    print 'Exporting records\n'
    for record in RECORDS.all():
        print 'Processing %s' % record.identifier
        if record.identifier.find(':') != -1:  # it's a URN
            # sanitize identifier
            print ' Sanitizing identifier'
            identifier = record.identifier.split(':')[-1]
        else:
            identifier = record.identifier
    
        # write to XML document
        FILENAME = os.path.join(xml_dirpath, '%s.xml' % identifier)
        try:
            print ' Writing to file %s' % FILENAME
            with open(FILENAME, 'w') as XML:
                XML.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                XML.write(record.xml)
        except Exception, err:
            raise RuntimeError("Error writing to %s" % FILENAME, err)
    
def refresh_harvested_records(database, url):
    ''' refresh / harvest all non-local records in repository '''
    from owslib.csw import CatalogueServiceWeb

    # get configuration and init repo connection
    REPOS = repository.Repository(database, 'records', {})

    # get all harvested records
    COUNT, RECORDS = REPOS.query(constraint={'where': 'source != "local"'})

    if int(COUNT) > 0:
        print 'Refreshing %s harvested records' % COUNT
        CSW = CatalogueServiceWeb(url)

        for rec in RECORDS:
            print 'Harvesting %s (identifier = %s) ...' % \
            (rec.source, rec.identifier)
            # TODO: find a smarter way of catching this
            schema = rec.schema
            if schema == 'http://www.isotc211.org/2005/gmd':
                schema = 'http://www.isotc211.org/schemas/2005/gmd/'
            CSW.harvest(rec.source, schema)
            print CSW.response
    print 'No harvested records to refresh'

def rebuild_db_indexes(database):
    ''' Rebuild database indexes '''
    pass

def optimize_db(database):
    ''' Optimize database '''
    print 'Optimizing %s' % database
    REPOS = repository.Repository(database, 'records', {})
    REPOS.connection.execute('VACUUM ANALYZE')

def usage():
    ''' Provide usage instructions '''
    return '''
NAME
    pycsw-admin.py - pycsw admin utility

SYNOPSIS
    pycsw-admin.py -c <command> -f <cfg> [-h] [-p /path/to/records]

    Available options:

    -c    Command to be performed (one of setup_db, load_records
          export_records, rebuild_db_indexes, optimize_db,
          refresh_harvested_records)

    -f    Filepath to pycsw configuration

    -h    Usage message

    -p    path to input/output directory to read/write metadata records

EXAMPLES

    1.) setup_db: Creates repository tables and indexes

        pycsw-admin.py -c setup_db -f default.cfg

    2.) load_records: Loads metadata records from directory into repository

        pycsw-admin.py -c load_records -p /path/to/records -f default.cfg

    3.) export_records: Dump metadata records from repository into directory

        pycsw-admin.py -c export_records -p /path/to/records -f default.cfg

    4.) rebuild_db_indexes: Rebuild repository database indexes

        pycsw-admin.py -c rebuild_db_indexes -f default.cfg

    5.) optimize_db: Optimize repository database

        pycsw-admin.py -c optimize_db -f default.cfg

    6.) refresh_harvested_records: Refresh repository records
        which have been harvested

        pycsw-admin.py -c refresh_harvested_records -f default.cfg
'''

COMMAND = None
XML_DIRPATH = None
CFG = None

if len(sys.argv) == 1:
    print usage()
    sys.exit(1)

try:
    OPTS, ARGS = getopt.getopt(sys.argv[1:], 'c:f:hp:')
except getopt.GetoptError, err:
    print '\nERROR: %s' % err
    print usage()
    sys.exit(2)

for o, a in OPTS:
    if o == '-c':
        COMMAND = a
    if o == '-p':
        XML_DIRPATH = a
    if o == '-f':
        CFG = a
    if o == '-h':  # dump help and exit
        print usage()
        sys.exit(3)

if COMMAND is None:
    print '-c <command> is a required argument'
    sys.exit(4)

if COMMAND not in ['setup_db', 'load_records', 'export_records', \
    'rebuild_db_indexes', 'optimize_db', 'refresh_harvested_records']:
    print 'ERROR: invalid command name: %s' % operation
    sys.exit(5)

if CFG is None:
    print 'ERROR: -f <cfg> is a required argument'
    sys.exit(6)

if COMMAND in ['load_records', 'export_records'] and XML_DIRPATH is None:
    print 'ERROR: -p </path/to/records> is a required argument'
    sys.exit(7)

SCP = SafeConfigParser()
SCP.readfp(open(CFG))

DATABASE = SCP.get('repository', 'database')
URL = SCP.get('server', 'url')
HOME = SCP.get('server', 'home')

if COMMAND == 'setup_db': 
    setup_db(DATABASE, HOME)
elif COMMAND == 'load_records':
    load_records(DATABASE, XML_DIRPATH)
elif COMMAND == 'export_records':
    export_records(DATABASE, XML_DIRPATH)
elif COMMAND == 'rebuild_db_indexes':
    rebuild_db_indexes(DATABASE)
elif COMMAND == 'optimize_db':
    optimize_db(DATABASE)
elif COMMAND == 'refresh_harvested_records':
    refresh_harvested_records(DATABASE, URL)

print 'Done'
