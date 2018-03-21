import os
from subprocess import Popen,PIPE
from shlex import split
from sys import exit
from re import search
from os import path

class Cmd(object):
    def __init__(self,command):
        self.command = command
        if "|" in self.command:
            cmd_parts = self.command.split('|')
        else:
            cmd_parts = []
            cmd_parts.append(self.command)
        i = 0
        p = {}
        for cmd_part in cmd_parts:
            cmd_part = cmd_part.strip()
            if i == 0:
                p[i]=Popen(split(cmd_part),stdin=None, stdout=PIPE, stderr=PIPE)
            else:
                p[i]=Popen(split(cmd_part),stdin=p[i-1].stdout, stdout=PIPE, stderr=PIPE)
            i += 1
        self.out,self.err = p[i-1].communicate()
        self.code = p[0].wait()
    
    def out(self):
        return self.out

    def err(self):
        return self.err

    def code(self):
        return self.code

class XenView(object):
    """ Class initializer """
    def __init__(self):
        self.domu_list = {}
        
    ''' Gets a list of running domUs '''
    def get_domus(final_check=False):
        if final_check:
            cmd = Cmd("xm list --state=running | grep -v Name")
        else:
            cmd = Cmd("xm list | grep -v Name")
        if cmd.code != 0:
            error("Unable to get domU list")
        for domu in cmd.out.splitlines():
            if "Domain-0" in domu:
                continue
            if domu.split()[1]:
                self.domu_list[domu.split()[1]] = domu.split()[0]
        return True

def main():
    xv = XenView()
    xv.get_domus()
    print(xm.domu_list)

if __name__ == '__main__': 
    main()
