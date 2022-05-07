# -*- coding: utf-8 -*-

from socket import timeout
import subprocess
import re
import datetime
import json

# GLOBALS
CELL_MEASUREMENT_BIN_PATH = "/home/ponga/radio/crocodilehunter/src/srsLTE/build/lib/examples/cell_measurement"
CELL_SEARCH_BIN_PATH = "/home/ponga/radio/srsRAN/build/lib/examples/cell_search"
CELL_SCAN_TIMEOUT = 60

BANDS = [1, 12, 13, 18, 19, 2, 20, 25, 26, 28, 3, 4, 5, 66, 71, 8, 85]


class CellSearch:
    def __init__(self):
        self.signals = []
        self.found_earfcns = []
        self.enodebs = []

    def _set_uniq_earfcn(self):
        earfcns = []
        for cell in self.signals:
            if cell["earfcn"] not in earfcns:
                earfcns.append(cell["earfcn"])
        self.found_earfcns = earfcns

    def reset(self):
        self.__init__()

    def search(self, band: int):
        print(f" + Searching on Band {band}")
        with subprocess.Popen(
            [CELL_SEARCH_BIN_PATH, "-b", str(band)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ) as proc:
            line_num = 0
            for line in proc.stdout:
                line_str = line.decode()
                matches = re.match("^\[\s*?[0-9]+?/[0-9]+?\]:", line_str)
                # if line_num < 10 and line_str[0] != "[" and line_str.find("Set RX") < 0 and not matches:
                #     print(f" + {line_str}", end="\r")
                if matches:
                    print(f"  {line_str.rstrip()}", end="\r", flush=True)
                if re.match("^Found CELL [0-9]", line_str):
                    s = self._parse_cell_search_results(line_str)
                    if s:
                        s["band"] = band
                        self.signals.append(s)
                line_num += 1
        self._set_uniq_earfcn()
        print("")

    def _scan(self, earfcns: list):
        use_list = False
        enodebs = []
        if not earfcns:
            use_list = True
            earfcns = self.found_earfcns
        for earfcn in earfcns:
            print(f"+ Scanning EARFCN {earfcn}...")
            start_ts = int(datetime.datetime.now().timestamp())
            with subprocess.Popen(
                [CELL_MEASUREMENT_BIN_PATH, "-z", str(earfcn)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            ) as proc:
                for line in proc.stdout:
                    # cell_measurement will spit out lots of output
                    # there are occasions where it won't find a MIB/SIB header and will just run forever. we dont want that
                    if int(datetime.datetime.now().timestamp()) > start_ts + CELL_SCAN_TIMEOUT:
                        print(f"! Timed out scanning EARFCN {earfcn}")
                        break
                    line_str = line.decode()
                    if line_str.find("Decoded MIB") > -1 or line_str.find("Decoded SIB") > -1:
                        pass
                        # print(f"+ {line_str}")
                    if line_str.find("**** sending packet: ") > -1:
                        s = self._parse_cell_scan_results(line_str)
                        if s:
                            enodebs.append(s)
                proc.kill()
                continue
        if use_list:
            self.enodebs += enodebs
        else:
            return enodebs

    def _parse_cell_search_results(self, result_str: str) -> dict:
        s = re.search("^Found CELL (.+?), EARFCN=(.+?), PHYID=(.+?), (.+?) PRB,.+?PSS power=(.+?)$", result_str)
        if len(s.groups()) != 5:
            return ""
        return {"freq": s.group(1), "earfcn": s.group(2), "phyid": s.group(3), "prb": s.group(4), "pss": s.group(5)}

    def _parse_cell_scan_results(self, result_str: str) -> dict:
        # print(result_str)
        s = re.search(
            "\<(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?),(.+?)\>",
            result_str,
        )
        if not s:
            return ""
        if len(s.groups()) != 17:
            return ""
        return {
            "mcc": s.group(1),
            "mnc": s.group(2),
            "tac": s.group(3),
            "cid": s.group(4),
            "phyid": s.group(5),
            "earfcn": s.group(6),
            "rssi": s.group(7),
            "freq": s.group(8),
            "enb_id": s.group(9),
            "sector_id": s.group(10),
            "_cfo": s.group(11),
            "rsrq": s.group(12),
            "snr": s.group(13),
            "rsrp": s.group(14),
            "tx_pwr": s.group(15),
            "_raw_sib1": s.group(16),
            "seconds": s.group(17),
        }


if __name__ == "__main__":
    cs = CellSearch()
    for band in BANDS:
        cs.search(band)
    # cs.search(4)
    # print(json.dumps(cs.signals, indent=4))
    print(cs.found_earfcns)
    # cs.found_earfcns = [5035,8763,5230,5892,675,522,524]
    cs._scan([])
    print(json.dumps(cs.enodebs, indent=4))
    print("Done.")
