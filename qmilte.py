# -*- coding: utf-8 -*-

# TODO: Write some things. And some stuff
"""
Occasionally, things will get weird. Sometimes I have to rmmod cdc_wdm and reload it Ex.
rmmod qmi_wwan; rmmod cdc_mbim; rmmod cdc_wdm; modprobe qmi_wwan
Othertime, reseting (power cycling the device does the trick.)
"""

import argparse
import subprocess
import re
import time
import csv
import sys
import threading
import datetime
import json
import typing

import earfcn_calc

# GLOBALS
QMICLI_BIN = "/usr/bin/qmicli"
MODEM_DEVICE = "/dev/cdc-wdm2"
QMI_PROXY_MODE = True
IS_QMI_BUSY = False
BAND_TABLE = {}
MCCMNC_TABLE = {}
QMI_SEARCH_CMD = "--nas-network-scan"
PRACH_TIMEOUT = 1
PRACH_RETRIES = 2


class Cell:
    def __init__(self):
        self.last_seen_ts = 0
        self.last_seen_str = 0
        self.plmn = "0"
        self.mcc = "0"
        self.mnc = "0"
        self.operator = ""
        self.cid = 0
        self.pci = 0
        self.tac = 0
        self.earfcn = 0
        self.freq_dl_mhz = 0.0
        self.band = 0
        self.rsrp_dbm = 0.0
        self.reg_status = ""
        self.risk_level = 7  # Risk Level: {0..10} where 0 is trustworthy and 10 is almost certainly an IMSI catcher
        self.api = []

    @staticmethod
    def _colorize_print(d: dict) -> str:
        bc = ""
        if d["risk_level"] > -1 and d["risk_level"] < 4:
            bc = bcolors.OKGREEN
        if d["risk_level"] > 3 and d["risk_level"] < 7:
            bc = bcolors.WARNING
        if d["risk_level"] > 6:
            bc = bcolors.FAIL
        print(f"{bc}{json.dumps(d,indent=4)}{bcolors.ENDC}")

    def __str__(self):
        return json.dumps(vars(self))

    def print(self):
        self._colorize_print(vars(self))


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def scan() -> dict:
    helpers = Helpers()
    global IS_QMI_BUSY
    spin_thread = threading.Thread(target=spin_cursor)
    cmd = [QMICLI_BIN, "-d", MODEM_DEVICE, ""]
    if QMI_PROXY_MODE:
        cmd.insert(1, "-p")
    modem_modem_str = ""
    cmd[len(cmd) - 1] = "--dms-get-manufacturer"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        for line in proc.stdout:
            if line.decode().find("Manufacturer:") > -1:
                modem_modem_str += line.decode().split(":")[1].strip("'").rstrip() + " "
    cmd[len(cmd) - 1] = "--dms-get-model"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        for line in proc.stdout:
            if line.decode().find("Model:") > -1:
                modem_modem_str += "Model: " + line.decode().split(":")[1].strip("'").rstrip() + ", "
    cmd[len(cmd) - 1] = "--dms-get-revision"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        for line in proc.stdout:
            if line.decode().find("Revision:") > -1:
                modem_modem_str += "Rev. " + line.decode().split(":")[1].strip("'").rstrip() + " "
    cmd[len(cmd) - 1] = "--dms-set-operating-mode=online"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        for line in proc.stdout:
            if line.decode().find("Operating mode set successfully") < 0:
                print(f"[!] ERROR when attempting to set operating mode for modem: {line.decode()}")
                return {}
    print(f"[+] Using modem {modem_modem_str}")
    cmd[len(cmd) - 1] = "--nas-network-scan"
    ret_strings = []
    print("[+] Running nas-network-scan... ", end="")
    IS_QMI_BUSY = True
    spin_thread.start()
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        for line in proc.stdout:
            ret_strings.append(line.decode())
    IS_QMI_BUSY = False
    spin_thread.join()
    spin_thread = threading.Thread(target=spin_cursor)
    if not ret_strings:
        print("[!] ERROR when attempting to perform network scan; Nothing was returned")
        return {}
    # Network [0]:
    # MCC: '310'
    # MNC: '260'
    # Status: 'current-serving, home, not-forbidden, preferred'
    # Description: 'T-Mobile'
    plmns = []
    for idx, line in enumerate(ret_strings):
        if re.match("Network \[[0-9{1,2}]\]:", line):
            re_m = re.search("\sMCC: '([0-9]{1,3})'", ret_strings[idx + 1])
            mcc = re_m.group(1)
            re_m = re.search("\sMNC: '([0-9]{1,3})'", ret_strings[idx + 2])
            mnc = re_m.group(1)
            plmns.append(helpers._resolve_plmn_from_str(mcc, mnc))
    if len(plmns) < 2:
        print(
            f"[*] WARN --nas-network-scan only returned {len(plmns)} results. Consider running with the -f option or power cycling your modem."
        )
    plmns = list(set(plmns))
    plmns.sort()
    print(f"[+] Found {len(plmns)} networks: {plmns}")
    cells = []

    for plmn in plmns:
        cell = Cell()
        cell.plmn = plmn
        cell.mcc = plmn[:3]
        cell.mnc = plmn[3:]
        for retry_num in range(PRACH_RETRIES):
            prach_timeout = PRACH_TIMEOUT + (retry_num * 3)
            cmd[len(cmd) - 1] = "--nas-set-system-selection-preference=lte,manual=" + plmn
            modem_ready = True
            print(f"[+]   Selecting PLMN {plmn}... ", end="")
            spin_thread = threading.Thread(target=spin_cursor)
            IS_QMI_BUSY = True
            spin_thread.start()
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
                for line in proc.stdout:
                    if line.decode().find("System selection preference set successfully") < 0:
                        print(f"[!] ERROR when attempting to Select Network {plmn}")
                        modem_ready = False
                        proc.kill()
                        break
            if not modem_ready:
                continue
            # if manually setting system selection, wait about for modem to complete PRACH
            time.sleep(prach_timeout)
            IS_QMI_BUSY = False
            spin_thread.join()
            ret_strings = []
            cmd[len(cmd) - 1] = "--nas-get-system-info"
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
                for line in proc.stdout:
                    ret_strings.append(line.decode())
            if not ret_strings:
                print("[!] ERROR when parsing nas-get-system-info")
                continue
            d = datetime.datetime.now()
            cell.last_seen_str = d.isoformat()
            cell.last_seen_ts = int(d.timestamp())
            mcc = 0
            mnc = 0
            for idx, line in enumerate(ret_strings):
                if line.find("LTE service:") > -1:
                    re_m = re.search("\sStatus: '(.+?)'", ret_strings[idx + 1])
                    if re_m:
                        cell.reg_status = re_m.group(1)
                    for lte_idx in range(idx + 2, len(ret_strings)):
                        re_m = re.search("\sCell ID: '(.+?)'", ret_strings[lte_idx])
                        if re_m:
                            cell.cid = int(re_m.group(1))
                        re_m = re.search("\sMCC: '(.+?)'", ret_strings[lte_idx])
                        if re_m:
                            mcc = re_m.group(1)
                        re_m = re.search("\sMNC: '(.+?)'", ret_strings[lte_idx])
                        if re_m:
                            mnc = re_m.group(1)
                        re_m = re.search("\sTracking Area Code: '(.+?)'", ret_strings[lte_idx])
                        if re_m:
                            cell.tac = int(re_m.group(1))
                        # ensure we are attached to the correct PLMN
            if mcc + mnc != plmn:
                print(f"[*]     PLMN mis-match '{mcc + mnc}' after PRACH attempt - Retrying {plmn} ({retry_num+1})")
                continue
            ret_strings = []
            cmd[len(cmd) - 1] = "--nas-get-cell-location-info"
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
                for line in proc.stdout:
                    ret_strings.append(line.decode())
            if not ret_strings:
                print("[!] ERROR when parsing nas-get-cell-location-info")
                continue
            for idx, line in enumerate(ret_strings):
                if line.find("Intrafrequency LTE Info") > -1:
                    re_m = re.search("\sEUTRA Absolute RF Channel Number: '(.+?)'", ret_strings[idx + 5])
                    if re_m:
                        cell.earfcn = int(re_m.group(1))
                    re_m = re.search("\sServing Cell ID: '(.+?)'", ret_strings[idx + 6])
                    if re_m:
                        cell.pci = int(re_m.group(1))
                    for j in range(20):
                        try:
                            if ret_strings[idx + j].find("Cell [0]:") > -1:
                                re_m = re.search("\sRSRP: '(.+?)'", ret_strings[idx + j + 3])
                                if re_m:
                                    cell.rsrp_dbm = float(re_m.group(1))
                                break
                        except IndexError:
                            pass
                    break
            # resolve some things
            if not cell.earfcn or type(cell.earfcn) != type(1):
                if retry_num < PRACH_RETRIES:
                    print(f"[*]     Retrying {plmn} ({retry_num+1})")
                    continue
                else:
                    print(f"[!] ERROR Could not obtain the EARFCN for PLMN {plmn}")
            else:
                cell.band = helpers.get_band_from_earfcn(cell.earfcn)
                cell.freq_dl_mhz = helpers.get_freq_from_earfcn(cell.band, cell.earfcn)
                cell.operator = helpers.get_operator(plmn)
                cells.append(cell)
                break
        # end for prach_retries
    # end for plmns
    # we should now have everything from QMICLI
    cmd[len(cmd) - 1] = "--dms-reset"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        pass
    IS_QMI_BUSY = False
    return cells


class Helpers:

    BAND_TABLE = {}
    MCCMNC_TABLE = {}

    def __init__(self):
        with open("blob/lteBandTable.json") as json_file:
            self.BAND_TABLE = json.load(json_file)

        with open("blob/mcc-mnc-table.csv", mode="r") as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                try:
                    m = int(row[0])
                    n = int(row[2])
                except ValueError:
                    continue
                self.MCCMNC_TABLE[self._resolve_plmn_from_str(row[0], row[2])] = {
                    "mcc": row[0],
                    "mnc": row[2],
                    "country_code": row[4].upper(),
                    "operator_name": row[7],
                }

    def _resolve_plmn_from_str(self, mcc: str, mnc: str) -> str:
        if len(mcc) == 1:
            mcc = "00" + mcc
        if len(mcc) == 2:
            mcc = "0" + mcc
        if len(mnc) == 1:
            mnc = "00" + mnc
        if len(mnc) == 2:
            mnc = "0" + mnc
        return mcc + mnc

    def get_band_from_earfcn(self, earfcn: int) -> int:
        for band in self.BAND_TABLE:
            if earfcn >= band["NDL_Min"] and earfcn < band["NDL_Max"]:
                return band["band"]
        return -1

    def get_freq_from_earfcn(self, band: int, earfcn: int) -> float:
        return earfcn_calc.earfcn2freq(band, dl_earfcn=earfcn)[0]

    def get_operator(self, plmn: str) -> str:
        operator = "[??] / _UNKNOWN_"
        try:
            operator = "[" + self.MCCMNC_TABLE[plmn]["country_code"] + "] / " + self.MCCMNC_TABLE[plmn]["operator_name"]
        except KeyError:
            # plmn not found. wtf. lets at least ID the country
            cos = {}
            for i in enumerate(self.MCCMNC_TABLE):
                if self.MCCMNC_TABLE[i[1]]["mcc"] == plmn[:3]:
                    cc = self.MCCMNC_TABLE[i[1]]["country_code"]
                    if cc in cos.keys():
                        cos[cc] += 1
                    else:
                        cos[cc] = 1
            operator = max(cos, key=cos.get) + " / __UNKNOWN_"
        return operator


def spin_cursor():
    while True:
        try:
            for cursor in "|/-\\":
                sys.stdout.write(cursor)
                sys.stdout.flush()
                time.sleep(0.1)
                sys.stdout.write("\b")
                if not IS_QMI_BUSY:
                    sys.stdout.write("\bdone.")
                    sys.stdout.write("\n")
                    return
        except KeyboardInterrupt:
            raise KeyboardInterrupt


if __name__ == "__main__":
    arg_parse = argparse.ArgumentParser(
        description="Use a Qualcomm modem and the excellent qmicli utility to perform a Site Survey of available LTE Service Providers in range."
    )
    arg_parse.add_argument(
        "-p",
        "--proxy",
        action="store_true",
        required=False,
        help="Use QMI Proxy mode to access the CDC device.",
    )
    arg_parse.add_argument(
        "-f",
        "--force",
        action="store_true",
        required=False,
        help="Force the modem to run a fresh Network Scan.",
    )
    arg_parse.add_argument(
        "-d",
        "--device",
        metavar="device",
        required=False,
        help="Specify the device path for the QMI interface. Otherwise assumed to be /dev/cdc-wdm0",
    )
    args = arg_parse.parse_args()
    if args.proxy:
        QMI_PROXY_MODE = True
    else:
        QMI_PROXY_MODE = False
    if args.device:
        MODEM_DEVICE = args.device
    else:
        MODEM_DEVICE = "/dev/cdc-wdm0"
    if args.force:
        QMI_SEARCH_CMD = "--nas-force-network-search"
    # do things
    s_time = int(datetime.datetime.now().timestamp())
    scan_results = scan()
    if not scan_results:
        exit(1)
    elapsed_time = int(datetime.datetime.now().timestamp()) - s_time
    strongest_signals = {}
    i = 0
    networks = []
    print("[+] Scan Complete.")
    print("")
    print("Results: ")
    for results in scan_results:
        networks.append(results.operator.split(" / ")[1])
        if results.rsrp_dbm != 0.0:
            strongest_signals[str(i)] = results.rsrp_dbm
        results.print()
        i += 1
    print("")
    print("Summary: ")
    print(f"  {len(scan_results)} Towers Found.")
    strongest_cell = scan_results[int(max(strongest_signals, key=strongest_signals.get))]
    sd = {
        "plmn": strongest_cell.plmn,
        "rsrp_dbm": strongest_cell.rsrp_dbm,
        "band": strongest_cell.band,
        "freq_dl_mhz": strongest_cell.freq_dl_mhz,
        "operator": strongest_cell.operator.split(" / ")[1],
    }
    print(f"  Network Operators: {list(set(networks))}")
    print(f"  Strongest Signal: {json.dumps(sd)}")
    print("")
    print(f"Scan completed in {elapsed_time} seconds.")
