#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import glob
import re
import sys
import socket
import optparse
from subprocess import Popen,PIPE

class XenView(object):
    class DOCMD(object):
        def __init__(self,command):
            self.command = command
            p = Popen(self.command, stdin=PIPE, stdout=PIPE, \
                stderr=PIPE, shell=True)
            self.out,self.err = p.communicate()
            self.code = p.returncode
        def out(self):
            return self.out
        def err(self):
            return self.err
        def code(self):
            return self.code

    """ Class initializer """
    def __init__(self, debug=False):
        ''' Final result with domu_id as key'''
        self.running_domu_name_dict = {}
        self.running_domu_disk_dict = {}
        self.running_domu_vm_cfg_dict = {}
        self.vm_cfg_dict = {}

        self.debug = debug

        ''' Interim result '''
        self.conf_path_dict = {}

    ''' Only to print debugging information '''
    def _dprint(self, msg):
        if self.debug:
            print('DEBUG: %s' % msg)

    ''' Gets a list of running domUs '''
    def _initialize_domu_list(self, running=True):
        if running:
            cmd = self.DOCMD("xm list --state=running | grep -v Name")
        else:
            cmd = self.DOCMD("xm list | grep -v Name")
        if cmd.code != 0:
            print("ERROR: Unable to get domU list")
            return

        for domu in cmd.out.splitlines():
            if "Domain-0" in domu:
                continue
            if domu.split()[1]:
                self.running_domu_name_dict[domu.split()[1]] = domu.split()[0]
        return True

    ''' Get img disk list path from xenstore for a given domU '''
    def _initialize_disk_for_domu(self, domu_id):
        backends = []
        disks = []
        cmd = self.DOCMD("xenstore-ls /local/domain/%s" % domu_id)
        if cmd.code != 0:
            return
        for line in cmd.out.splitlines():
            if re.search("backend =.*vbd",line):
                backends.append(line.split("=")[1].replace('"',''))

        for back in backends:
            cmd = self.DOCMD("xenstore-ls -f %s | grep params" % back)
            if cmd.code != 0:
                return
            disks.append(cmd.out.split("=")[1].replace('"','').strip())

        self.running_domu_disk_dict[domu_id] = disks
        return True

    def _initialize_disk_list(self):
        if len(self.running_domu_name_dict) == 0:
            return
        for domu_id in self.running_domu_name_dict.keys():
            self._initialize_disk_for_domu(domu_id)

    def _get_file_content(self, filename):
        fo = open(filename)
        lines = fo.readlines()
        new_lines = []
        for line in lines:
            line = line.strip()
            if line == '' or line[0] == '#':
                continue
            new_lines.append(line)
        fo.close()
        return new_lines

    def _initialize_conf_list(self):
        conf_path = '%s/conf/vm_cfg_path.json' % os.path.dirname(os.path.realpath(__file__))
        self.conf_path_dict = json.load(open(conf_path))

    def _get_domain_name_from_file(self, filename):
        if not os.path.isfile(filename):
            return ''

        contents = self._get_file_content(filename)

        domain_name = ''
        for content in contents:
            if not re.search('name\s*=', content):
                continue
            pos = content.find('=')
            domain_name = content[pos+1:]
            domain_name = domain_name.strip().strip('\"').strip('\'')
            break
        return domain_name
                
    def _update_vm_cfg_dict(self, domain_name, vmcfg_path):
        if len(domain_name) == 0 or len(vmcfg_path) == 0:
            return

        if domain_name in self.vm_cfg_dict.keys():
            if self.vm_cfg_dict[domain_name] != vmcfg_path:
                self._dprint('Domain %s conflicted: path1: %s; path2: %s' % (domain_name, self.vm_cfg_dict[domain_name], vmcfg_path))
                return
        else:
            self.vm_cfg_dict[domain_name] = vmcfg_path
            
    
    ''' Case 1: FA SaaS: /root/${hostname}.vms which used by /etc/rc.d/init.d/dom0init '''
    def _case1(self):
        if not os.path.exists('/etc/rc.d/init.d/dom0init'):
            return
        hostname = socket.gethostname()
        filename = '/root/%s.vms' % hostname
        if not os.path.isfile(filename):
            return
        
        lines = self._get_file_content(filename)
        for line in lines:
            if os.path.basename(line) != 'vm.cfg':
                continue
            domain_name_in_vm_cfg = self._get_domain_name_from_file(line)
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, line)

    ''' Case 2: xendomains: /etc/xen/auto, usually symbolic link'''
    def _case2(self):
        path_regex = '/etc/xen/auto/*'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name1 = os.path.basename(file_name)
            if os.path.islink(file_name):
                file_name = os.path.realpath(file_name)
            if os.path.basename(file_name) != 'vm.cfg':
                continue
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            if domain_name1 != domain_name_in_vm_cfg:
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 3: PDIT EIS Managed VM : '/xen/*/vm.cfg' (ubamx4060)'''
    def _case3(self):
        path_regex = '/xen/*/vm.cfg'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name_in_path = file_name.split('/')[-2]
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            if domain_name_in_path != domain_name_in_vm_cfg:
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 4: PDIT DEV OVS 3.x: /OVS/Repositories/3914FD9CE3E74C5D8A83BC8BE69764E5/VirtualMachines/bej312378/vm.cfg (bejaq30)'''
    def _case4(self):
        path_regex = '/OVS/Repositories/*/VirtualMachines/*/vm.cfg'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name_in_path = file_name.split('/')[-2]
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            if domain_name_in_path != domain_name_in_vm_cfg:
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 5: PDIT DevOps Managed OVM 2.2 VM: /etc/xen/domU/domU_*  (bej0201)'''
    def _case5(self):
        path_regex = '/etc/xen/domU/domU_*'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name_in_path = os.path.basename(file_name).split('_')[-1]
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            if domain_name_in_path != domain_name_in_vm_cfg:
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 6: VM Manager 2.2 Managed VM: /var/ovs/mount/*/running_pool/*/vm.cfg (bejxax13)'''
    def _case6(self):
        path_regex = '/var/ovs/mount/*/running_pool/*/vm.cfg'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name_in_path = file_name.split('/')[-2]
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            '''
                Special handling here domain_name_in_vm_cfg is not fully matched with domain_name_in_path
                    [root@bejxax13 xenview]# ls -al /var/ovs/mount/882F2D2FF05B40A3988B6BD3E3DFB616/running_pool/bejxaia39_cn_oracle_com/vm.cfg
                    -rw-r--r--+ 1 root root 570 Mar  8 06:42 /var/ovs/mount/882F2D2FF05B40A3988B6BD3E3DFB616/running_pool/bejxaia39_cn_oracle_com/vm.cfg

                    [root@bejxax13 xenview]# grep name /var/ovs/mount/882F2D2FF05B40A3988B6BD3E3DFB616/running_pool/bejxaia39_cn_oracle_com/vm.cfg
                    name = 'bejxaia39'
            '''
            if domain_name_in_path != domain_name_in_vm_cfg and not re.search('/%s_' % domain_name_in_vm_cfg, file_name):
                self._dprint('Domain Name Mismatch: file_name: %s, domain_name_in_path: %s, domain_name_in_vm_cfg: %s' % (file_name, domain_name_in_path, domain_name_in_vm_cfg))
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 7: OVM Manager 2.1.x Managed domU: /OVS/running_pool/*/vm.cfg (fpclmd0009.uspp1.oraclecloud.com)'''
    def _case7(self):
        path_regex = '/OVS/running_pool/*/vm.cfg'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name_in_path = file_name.split('/')[-2]
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            if domain_name_in_path != domain_name_in_vm_cfg and not re.search('/%s_' % domain_name_in_vm_cfg, file_name):
                self._dprint('Domain Name Mismatch: file_name: %s, domain_name_in_path: %s, domain_name_in_vm_cfg: %s' % (file_name, domain_name_in_path, domain_name_in_vm_cfg))
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 8: PDIT A&P Managed VM in CDC Lab: /xen_local/*/ (NOT TESTED DUE TO NO SYSTEM)'''
    def _case8(self):
        path_regex = '/xen_local/*/vm.cfg'
        file_list = glob.glob(path_regex)
        for file_name in file_list:
            domain_name_in_path = file_name.split('/')[-2]
            domain_name_in_vm_cfg = self._get_domain_name_from_file(file_name)
            if domain_name_in_path != domain_name_in_vm_cfg and not re.search('/%s_' % domain_name_in_vm_cfg, domain_name_in_path):
                self._dprint('Domain Name Mismatch: file_name: %s, domain_name_in_path: %s, domain_name_in_vm_cfg: %s' % (file_name, domain_name_in_path, domain_name_in_vm_cfg))
                continue
            self._update_vm_cfg_dict(domain_name_in_vm_cfg, file_name)

    ''' Case 9: Based on the xenstore-ls, find the vm.cfg on same path as img file '''
    def _case9(self):
        self._initialize_domu_list()
        self._initialize_disk_list()
        for domu_id in self.running_domu_disk_dict.keys():
            ''' Assume all disks are in the same dir '''
            disk_path = self.running_domu_disk_dict[domu_id][0]
            domain_name = self.running_domu_name_dict[domu_id]
            vm_cfg_path = '%s/vm.cfg' % os.path.dirname(disk_path)
            domain_name_in_vm_cfg = self._get_domain_name_from_file(vm_cfg_path)
            if len(domain_name_in_vm_cfg) != 0:
                if domain_name_in_vm_cfg == domain_name:
                    self._update_vm_cfg_dict(domain_name, vm_cfg_path)
                else:
                    self._dprint('file_name: %s, domain_name: %s, domain_name_in_vm_cfg: %s' % (vm_cfg_path, domain_name, domain_name_in_vm_cfg))
    
    def get_all_domu_name_2_vm_cfg_dict(self):
        if len(self.vm_cfg_dict) == 0:
            self._case1()
            self._case2()
            self._case3()
            self._case4()
            self._case5()
            self._case6()
            self._case7()
            self._case8()
            self._case9()
        return self.vm_cfg_dict
    
    def get_all_domu_name_2_vm_cfg_report(self):
        vmcfg_dict = self.get_all_domu_name_2_vm_cfg_dict()
        domu_name_list = vmcfg_dict.keys()
        domu_name_list.sort()
        self._dprint('===== Final Result: =====')
        for domu_name in domu_name_list:
            print('%s|%s' % (domu_name, vmcfg_dict[domu_name]))

def parse_opts():
    """Parse program options."""
    parser = optparse.OptionParser(description='Generate pairs of Xen VM name and configuration file path')
    parser.add_option('-d', '--debug', help='Turn on debug information', action='store_true', dest='debug', default=False)
    (opts, args) = parser.parse_args()
    return (opts, args)

    
def main():
    (opts, args) = parse_opts()
    xv = XenView(opts.debug)
    xv.get_all_domu_name_2_vm_cfg_report()

if __name__ == '__main__':
    main()
