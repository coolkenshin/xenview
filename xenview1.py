#!/usr/bin/python

import os
import glob
import re
import sys
import pprint
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
    def __init__(self, init_disk=False, debug=False):
        ''' Final result with domu_id as key'''
        self.domu_dict = {}
        self.disk_dict = {}
        self.vm_cfg_dict = {}

        self.debug = debug

        ''' Interim result '''
        self.conf_path_list = []
        self.possible_vm_cfg_list = []

        self._initialize_conf_list()
        self._initialize_domu_list()
        if init_disk:
            self._initialize_disk_list()

    def _dprint(self, msg):
        if self.debug:
            print(msg)

    ''' Gets a list of running domUs '''
    def _initialize_domu_list(self, final_check=False):
        if final_check:
            cmd = self.DOCMD("xm list --state=running | grep -v Name")
        else:
            cmd = self.DOCMD("xm list | grep -v Name")
        if cmd.code != 0:
            error("Unable to get domU list")
        for domu in cmd.out.splitlines():
            if "Domain-0" in domu:
                continue
            if domu.split()[1]:
                self.domu_dict[domu.split()[1]] = domu.split()[0]
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

        self.disk_dict[domu_id] = disks
        return True

    def _initialize_disk_list(self):
        if len(self.domu_dict) == 0:
            return
        for domu_id in self.domu_dict.keys():
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
        conf_path = '%s/conf/vm_cfg_path.config' % os.path.dirname(os.path.realpath(__file__))
        dir_list = self._get_file_content(conf_path)
        self.conf_path_list = ' '.join(dir_list)

    def _is_ignored(self, file_path):
        IGNORE_LIST = [
            '\.bk',
            '\.bak',
            '\.orig',
            'old',
            'txt$',
            '\.auto',
            'snapshot',
            'Templates',
            '\.log$',
            'backup',
            '\.out$',
            'bkp',
            'bkup',
            'Jan',
            'Feb',
            'Mar',
            'Apr',
            'May',
            'Jun',
            'Jul',
            'Aug',
            'Sep',
            'Oct',
            'Nov',
            'Dec',
            '2010',
            '2011',
            '2012',
            '2013',
            '2014',
            '2015',
            '2016',
            '2017',
            '2018',
            'pre',
            'befor',
            'after',
            'upgrade',
            'recover',
            '\.ks$'
        ]
        for regex in IGNORE_LIST:
            if re.search(regex, os.path.basename(file_path), re.IGNORECASE):
                return True
        return False

    def _get_all_possible_vm_cfg_list(self):
        cmd = 'find %s -maxdepth 1 -type f -exec grep -Iq . {} \; -print 2>&1 |grep -v "No such file"' % self.conf_path_list
        #print(cmd)
        cmd_res = self.DOCMD(cmd)
        if cmd_res.code != 0:
            print("Error: command failed: %s" % cmd)
            return []

        res_list = cmd_res.out.splitlines()
        res_size = len(res_list)
        if res_size == 0:
            print("Error: size is 0")
            return []

        ''' Special handling of .vms file '''
        res_list2 = []
        for file_path in res_list:
            if re.search("\.vms$", file_path):
                lines = self._get_file_content(file_path)
                res_list2 += lines
            else:
                res_list2.append(file_path)

        ''' Filter those files that could be ignored '''
        res_list3 = []
        for file_path in res_list2:
            if not os.path.isfile(file_path):
                continue
            if self._is_ignored(file_path):
                continue
            res_list3.append(file_path)
        ''' Make it unique '''
        self.possible_vm_cfg_list = list(set(res_list3))
        return self.possible_vm_cfg_list

    def initialize_vm_cfg_dict(self):
        if len(self.possible_vm_cfg_list) == 0:
            self._get_all_possible_vm_cfg_list()

        for domu_id in self.domu_dict.keys():
            domu_name = self.domu_dict[domu_id]
            self.vm_cfg_dict[domu_id] = ''

            domu_vmcfg_path_list = []
            for vmcfg_path in self.possible_vm_cfg_list:
                lines = self._get_file_content(vmcfg_path)
                for line in lines:
                    if re.search("name\s*=", line):
                        if re.search(domu_name, line):
                            domu_vmcfg_path_list.append(vmcfg_path)
            if len(domu_vmcfg_path_list) == 1:
                self.vm_cfg_dict[domu_id] = domu_vmcfg_path_list[0]
            elif len(domu_vmcfg_path_list) == 0:
                self._dprint('DEBUG: WARN: No VM configuration file found for domu_id:%s; domu_name:%s' % (domu_id, domu_name))
            else:
                ''' If there are still multiple vm.cfg matched, we will only choose vm.cfg$ '''
                paths = []
                for path in domu_vmcfg_path_list:
                    if re.search("vm.cfg$", path):
                        paths.append(path)
                if len(paths) == 1:
                    self.vm_cfg_dict[domu_id] = paths[0]
                elif len(paths) == 0:
                    self._dprint('DEBUG: WARN: Multiple VM configurations file found for domu_id:%s; domu_name:%s' % (domu_id, domu_name))
                    self._dprint('\n'.join(domu_vmcfg_path_list))
                else:
                    self._dprint('DEBUG: WARN: Multiple VM configurations file found for domu_id:%s; domu_name:%s' % (domu_id, domu_name))
                    self._dprint('\n'.join(paths))


def unit_test():
    xv = XenView(debug=True)
    xv.initialize_vm_cfg_dict()
    #print('===== All possible VM CFG: =====\n' + '\n'.join(xv.possible_vm_cfg_list))
    print('===== Final Result: =====')
    pprint.pprint(xv.vm_cfg_dict)

if __name__ == '__main__':
    unit_test()
