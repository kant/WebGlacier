"""
Routines for fetching/writing/initialising
application wide data.
"""

#External dependency imports
import os,re,sqlalchemy
from datetime import datetime
from boto.glacier.layer1 import Layer1
from boto import glacier

#Flask imports
from flask import request, session

#WebGlacier imports
import WebGlacier as WG

def update_live_clients():
  """
  Check how long it has been since the last check-in and drops any clients that
  have missed too many check-ins.
  """
  now=datetime.utcnow()
  kill_em_all=[]
  for client,dat in WG.live_clients.iteritems():
    last_seen,poll_freq,processing = dat
    delta=(now-last_seen).total_seconds()
    nmiss = delta/poll_freq
    if nmiss > 5 and not processing:
      kill_em_all.append(client)
  #Do the killing outside the iteration loop to avoid stupidity
  for hit in kill_em_all:
    _ = WG.live_clients.pop(hit)

def get_valid_clients():
  """
  Determine which of the client are connected and have a valid IP.
  If it's in the list, put the current client first.
  """
  #Update the clients first
  update_live_clients()
  #Now get the clients that match this ip and are live
  webip=str(request.remote_addr)
  passed=[]
  for client in WG.live_clients.keys():
    cip = client[client.rfind("(")+1:-1] if client[-1]==")" else client
    if cip == webip:
      passed.append(client)
  #Put the current one at the front if it's in it
  if WG.app.config['current_client'] in passed:
      passed.insert(0,passed.pop(passed.index(WG.app.config['current_client'])))
  return passed

def get_set_region():
  """
  Gets the current region by looking first in url args, then in the session object, finally reverting to default.
  """
  if 'region' in request.args and request.args['region'] in WG.handlers:
    return request.args['region']
  elif 'region' in session and session['region'] in WG.handlers:
    return session['region']
  return WG.app.config["DEFAULT_REGION"]

def get_handler(region=None):
  """
  Get the active handler
  """
  return WG.handlers[get_set_region()] if region is None else WG.handlers[region]

def save_settings(data,cfile):
  """
  Update the settings file specified in cfile with
  the data in data.
  """
  #Options that if empty, don't change
  empty_no_change=["SQL_PASSWORD"]
  #No need to encase these in quotes
  no_quote=["DEBUG","APP_HOST","SQLALCHEMY_POOL_RECYCLE","UCHUNK","DCHUNK","SQL_PORT"]
  #First get the file name of the current settings file
  nome=os.environ.get("GLACIER_CONFIG",cfile)
  fdat=open(nome,'rb').read()
  #Save either the current setting, or the new one if validated
  for conf in data.keys():
    if conf in empty_no_change and data[conf]=='':
      continue
    if data[conf]!=WG.app.config.get(conf):
      if conf in no_quote:
        fdat=re.sub("(^|\n)"+str(conf)+"( |=).*","\\1"+str(conf)+" = "+str(data[conf]),fdat)
      else:
        fdat=re.sub("(^|\n)"+str(conf)+"( |=).*",'\\1'+str(conf)+' = """'+str(data[conf])+'"""',fdat)
  f=open(nome,'wb')
  f.write(fdat)
  f.close()

def build_db_key(dialect,db_name,hostname='',username='',password='',driver='',port=None):
  """
  Constructs a string that can be used with SQLalchemy to access a SQL database
  """
  #The command for sqlalchemy
  key=dialect
  if driver!='':
    key = key+"+"+driver
  tmp=":////" if dialect == "sqlite" else "://"
  key=key+tmp
  extra_slash=False
  if username!='' and password!='':
    extra_slash=True
    key=key+username+":"+password+"@"
  if hostname!='':
    extra_slash=True
    key = key+hostname
    if port is not None:
      key = key+":"+port
  if extra_slash:
    key=key+"/"
  key = key+db_name
  return key

def validate_db(key):
  """
  Try to connect to the SQL database with the provided parameters.
  If the function executes without errors, all is well.
  """
  a=sqlalchemy.engine.create_engine(key)
  b=a.connect()
  b.close()

def validate_glacier(access_key,secret_access_key,region):
  """
  Validate connection to Amazon Glacier
  If the function executes without errors, all is well.
  """
  tst = Layer1(aws_access_key_id = access_key,aws_secret_access_key = secret_access_key,region_name = region)
  a=tst.list_vaults()
  tst.close()

def init_handlers_from_config():
  """
  Use the config to create handlers for Amazon Glacier
  """
  for region in glacier.regions():
    WG.handlers[region.name] = Layer1(aws_access_key_id = WG.app.config["AWS_ACCESS_KEY"], aws_secret_access_key = WG.app.config["AWS_SECRET_ACCESS_KEY"],region_name=region.name)