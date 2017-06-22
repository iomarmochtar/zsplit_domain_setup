#!/usr/bin/env python

__author__ = ('Imam Omar Mochtar')
__email__ = ('iomarmochtar@gmail.com',)

"""
Script for migrating partially zimbra accounts. use case: zimbra OSE to NE split domain
"""

import os
import pwd
import grp
import sys
import ldap
import logging
from logging import FileHandler, StreamHandler, Formatter
from collections import OrderedDict
from pprint import pprint
from ConfigParser import ConfigParser
from ozpy.zmprov import Zmprov

ldap.set_option(ldap.OPT_REFERRALS, 0)
ldap.set_option(ldap.OPT_PROTOCOL_VERSION, 3)


def logExit(msg, retcode=1):
	sys.stderr.write("{}\n".format(msg))
	sys.exit(retcode)

class Zmbr(object):
	"""
	Instance/wrapper for zimbra server instance (source/target)
	"""
	__conf = None
	__zmbr = None
	__ldp = None

	def __init__(self, conf):
		self.__conf = conf
		self.__initZsoap()
		self.__initLdap()

	def __initZsoap(self):
		"""
		Initialize zimbra soap
		"""
		host = "https://{}:{}/service/admin/soap".format(
			self.__conf['host'], self.__conf['admin_port']
		)

		self.__zmbr = Zmprov(
			username=self.__conf['username'],
			password=self.__conf['password'],
			soapurl=host
		)

	def __initLdap(self):
		"""
		Initialize zimbra ldap connection
		"""
		url = "ldap://{}:{}".format(self.__conf['host'], self.__conf['ldap_port'])
		bind_dn = "uid=zimbra,cn=admins,cn=zimbra"
		self.__ldp = ldap.initialize(url)
		self.__ldp.simple_bind_s(bind_dn, self.__conf['ldap_pwd'])


	def _lSearch(self, sfilter, retattrs=[]):
		"""
		Ldap search wrapper
		"""
		result = []

		lri = self.__ldp.search(
			self.__conf['ldap_base'], ldap.SCOPE_SUBTREE,
			sfilter, retattrs
		)

		while True:
			result_type, result_data = self.__ldp.result(lri, 0)
			if (result_data == []):
				break
			else:
				if result_type == ldap.RES_SEARCH_ENTRY:
					result.append( result_data )

		return result


	def lock(self, attrs):
		"""
		Set account status to locked
		"""
		user_id = attrs['zimbraId']
		return self.__zmbr.ma(user_id, 'zimbraAccountStatus', 'locked')

	def unlock(self, attrs):
		"""
		Set account status to active
		"""
		user_id = attrs['zimbraId']
		return self.__zmbr.ma(user_id, 'zimbraAccountStatus', 'active')

	def setMailTransport(self, attrs, host):
		"""
		Set mail transport
		"""
		user_id = attrs['zimbraId']
		host = 'lmtp:{}:7025'.format(host)
		return self.__zmbr.ma(user_id, 'zimbraMailTransport', host)

	def setHashPwd(self, attrs):
		"""
		Change user userPassword directly to ldap
		"""
		dn = attrs['dn']
		# set hash password
		pwd = [
			(ldap.MOD_REPLACE, 'userPassword',
			[attrs['userPassword']])
		]
		self.__ldp.modify_s(dn, pwd)

	def createUser(self, attrs):
		"""
		Create zimbra user using soap instance
		"""
		mail = attrs['zimbraMailDeliveryAddress']
		nattrs = [
			{'_content': y, 'n': x} for x,y in attrs.iteritems()\
			if x in ['sn', 'givenName', 'diplayName', 'description']
		]
		# set for temporary password
		props = {
			"name": mail,
			"password": "TemPhoraryPWDD--",
			"attrs": nattrs
		}

		# self.conn.modify_s(user_dn, add_pass)
		user = self.__zmbr.ca(**props)
		if not user:
			return False

		return user

	def getUser(self, email):
		"""
		get user ldap data by it's email
		"""
		search = 'zimbraMailDeliveryAddress={}'.format(email)
		retattr = [
			'zimbraMailDeliveryAddress',
			'zimbraMailAlias', 'cn',
			'description', 'sn',
			'displayName', 'givenName',
			'userPassword', 'zimbraId'
		]
		user = self._lSearch(search, retattr)

		if not user:
			return None

		# cleanup data
		ret = {}
		for k, v in user[0][0][1].iteritems():
			ret[k] = v[0] if len(v) == 1 else v

		# if attribute doesn't exist then create with blank value
		for chk in retattr:
			if chk not in ret.keys():
				ret[chk] = ''

		ret['dn'] = user[0][0][0]
		return ret


class Migrate(object):

	confs = None

	tgt = None
	src = None
	migrate_list = []
	def __init__(self, mconf, tconf, sconf, zmzconf):
		"""
		mconf: main configuration
		tconf: target configuration
		sconf: source configuration
		zmzconf: zmz configuration
		"""
		list_file = mconf['list_file']

		if not os.path.isfile(list_file):
			logExit("List file is not found")

		self.migrate_list = [x.strip()\
		 for x in open(list_file, 'r').readlines() ]

		if not self.migrate_list:
			logExit("Empty migration list file")

		self.confs = {
			'mconf': mconf,
			'tconf': tconf,
			'sconf': sconf,
			'zmzconf': zmzconf
		}
		self.tgt = Zmbr(tconf)
		self.src = Zmbr(sconf)

		# setup logger
		log_lvl = logging.DEBUG
		self.log = logging.getLogger('migration')
		self.log.setLevel(log_lvl)
		formatter = Formatter(
			'%(asctime)s - %(name)s - %(levelname)s - %(message)s')


		# file hanlder
		fh = FileHandler(mconf['log_file'], 'a')
		fh.setLevel(log_lvl)
		fh.setFormatter(formatter)

		# console handler
		ch = StreamHandler()
		ch.setLevel(log_lvl)
		ch.setFormatter(formatter)

		self.log.addHandler(fh)
		self.log.addHandler(ch)


	def doConfirm(self, migrate_list):
		"""
		Confirm for user that will be migrated
		"""
		for migrate in migrate_list:
			print "Email: {}, DisplayName: {}".format(
				migrate['zimbraMailDeliveryAddress'],
				migrate['displayName']
			)

		while True:
			chk = raw_input("Continue (y/n) ?")
			chk = chk.strip().lower()

			if chk == 'y':
				break
			elif chk == 'n':
				sys.exit(0)


	def switchAccounts(self, migrate_list):
		"""
		Switch account from old system (source) to new one (target)
		"""
		for migrate in migrate_list:
			mail = migrate['zimbraMailDeliveryAddress']
			account = self.tgt.getUser(mail)
			if not account:
				self.log.info("{} not found on target, do create account procedure".format(mail))
				if not self.tgt.createUser(migrate):
					logExit("Cannot create {}".format(mail))

			# set hash password & also activate account
			self.log.info("{} set target account hash pwd {}".format(mail, migrate['userPassword']))
			self.tgt.setHashPwd(migrate)
			self.log.info("{} set target account status to active".format(mail))
			self.tgt.unlock(migrate)

			# disable (lock) status for source account
			self.log.info("{} set source account status to lock".format(mail))
			self.src.lock(migrate)

			tgt_host = self.confs['tconf']['host']
			# set zimbraMailTransport to new system (target) for target account
			self.log.info("{} set source mail transport to {}".format(mail, tgt_host))
			self.src.setMailTransport(migrate, tgt_host)

			# set zimbraMailTransport to server it self for make sure there will be no mail loop
			self.log.info("{} set target mail transport to {}".format(mail, tgt_host))
			self.tgt.setMailTransport(migrate, tgt_host)


	def genZmzConf(self):
		"""
		generating zmztozmig configuration
		"""
		zmz = OrderedDict()
		zmz['SourceZCSServer'] = self.confs['sconf']['host']
		zmz['SourceAdminUser'] = self.confs['sconf']['username']
		zmz['SourceAdminPwd'] = self.confs['sconf']['password']
		zmz['SourceAdminPort'] = '7071'

		zmz['TargetZCSServer'] = self.confs['tconf']['host']
		zmz['TargetAdminUser'] = self.confs['tconf']['username']
		zmz['TargetAdminPwd'] = self.confs['tconf']['password']
		zmz['TargetAdminPort'] = '7071'

		zmz['Threads'] = self.confs['zmzconf']['threads']
		wdir = self.confs['zmzconf']['working_dir']
		zmz['WorkingDirectory'] = os.path.join(wdir, 'mailboxdumps/')
		zmz['SuccessDirectory'] = os.path.join(wdir, 'successes/')
		zmz['LogDirectory'] = self.confs['zmzconf']['log_dir']
		zmz['KeepSuccessFiles'] = 'TRUE' if self.confs['zmzconf']['keep_success'] else 'FALSE'

		zmz['Domains'] = self.confs['zmzconf']['domains']

		zmz['Accounts'] = ','.join(self.migrate_list)

		with open(self.confs['zmzconf']['gen_conf_path'], 'w') as tmp:
			for k,v in zmz.iteritems():
				tmp.write("{}={}\n".format(k,v))

		# change ownership to zimbra user and group so zmztozmig command can read it
		os.chown(
			self.confs['zmzconf']['gen_conf_path'],
			pwd.getpwnam("zimbra").pw_uid,
			grp.getgrnam("zimbra").gr_gid
		)

	def run(self):
		"""
		Main coroutine
		"""
		migrateme = []
		for email in self.migrate_list:
			user = self.src.getUser(email)
			if not user:
				logExit("Email {} is not found".format(email))

			migrateme.append( user )

		# confirmation
		self.doConfirm(migrateme)
		self.log.info("Account switching migration begin")

		# switch
		self.switchAccounts(migrateme)

		# generating zmzconf
		gen_conf = self.confs['zmzconf']['gen_conf_path']
		self.log.info("generating zmztozmig configuration {}".format(gen_conf))
		self.genZmzConf()

		self.log.info("END OF SCRIPT")
		
		# show instruction after script has done it's work
		cmd = "{} -f {}".format(
			self.confs['zmzconf']['bin_path'],
			gen_conf
		)
		print "Run this command to migrate user data as zimbra user"
		print "zmprov fc all"
		print cmd

if __name__ == "__main__":

	BASE_DIR = os.path.dirname(os.path.abspath(__file__))
	MAIN_CONF = os.path.join(BASE_DIR, 'config.ini')

	if not os.path.isfile(MAIN_CONF):
		logExit("main configuration not found")

	parser = ConfigParser()
	parser.read(MAIN_CONF)

	mconf = dict(parser.items('main'))
	zmzconf = dict(parser.items('zmz'))
	tconf = dict(parser.items('target'))
	sconf = dict(parser.items('source'))

	Migrate(mconf, tconf, sconf, zmzconf).run()
