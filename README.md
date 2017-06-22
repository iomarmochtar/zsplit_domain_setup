Script for automating user migration in Zimbra split domain environment (https://wiki.zimbra.com/wiki/Split_Domain)

Utilizing zmztozmig command, event Zimbra it self not recommend it (https://wiki.zimbra.com/wiki/Zimbra_to_Zimbra_Migration) but so far it's the best way for do migration Zimbra to Zimbra environment because it's include calendar data migration, etc. (as far as this script written)

**note:** This script is created for single server only, you may modify it if in Zimbra multiserver environment.


These are what this script will do:
------------------------------------
1. Read users data from source server by user list that will be migrated
2. Create user if doesn't exist in target server
3. Set hash password for (new) user in target server
4. Set account status to locked in source server
5. Change zimbraMailTransport to target server for source server account
6. Generating zmztozmig configuration file


Setup
=====

**note:** This script require Python version 2.7, if in your Linux doesn't shipped it (Centos < 7 for instance). i recommend you to install Miniconda with version 2.7 (https://conda.io/miniconda.html)

Assuming your working directory for this script is **/root/local**

Clone the repository
```bash
git clone https://github.com/iomarmochtar/zsplit_domain_setup /root/local
cd /root/local
```


Install all required library
```bash
pip install -r requirements.txt
```


Copy example configuration and adjust it with your environment.

**note:** ldap_pwd configuration is for DN uid=zimbra,cn=admins,cn=zimbra, run command **zmlocalconfig -s ldap_root_password** as zimbra user to fetch it.
```bash
cp config.ini_dist config.ini
vim config.ini
```

Run the script
```bash
python split_domain_setup.py
```
