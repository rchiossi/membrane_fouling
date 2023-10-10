#!/usr/bin/env python 

import argparse
import numpy as np
import sys

from enum import IntEnum
from sklearn.linear_model import LinearRegression
from sklearn.utils import parse_version


class Column(IntEnum):
    TIME = 0
    PRESSURE = 1
    VOLUME = 2
    TEMPERATURE = 3


class MembraneFouling:
    def __init__(self, date: str, time: str, sdi: str, ti: str, tf: str, status: str):
        self.date = date.split(",")[1]
        self.time = time.split(",")[1]
        self.sdi = float(sdi.split(",")[1])
        self.ti = float(ti.split(",")[1])
        self.tf = float(tf.split(",")[1])
        self.status = status.split(",")[1]

        self.data:list[list[float]] = []


    def __str__(self):
        return f"Membrane Fouling [date:{self.date}, time:{self.time}, sdi:{self.sdi}, ti:{self.ti}, tf:{self.tf}, status:{self.status}]" 


    def add_data(self, raw) -> None:
        self.data.append([float(x) for x in raw.split(",")])


    def search_index(self, column: Column, value: float) -> tuple[int, list[float]]:
        closest = self.data[1]
        closest_index = 1

        for n, d in enumerate(self.data):
            if abs(d[column] - value) < abs(closest[column] - value):
                closest = d
                closest_index = n

        return closest_index, closest


    def search(self, column: Column, value: float) -> list[float]:
        _, res = self.search_index(column, value)
        return res

    
    def calc_ti(self) -> float:
        data = self.search(Column.VOLUME, 500)
        return data[Column.TIME]


    def calc_tf5(self) -> float:
        v5 = self.search(Column.TIME, 5*60)[Column.VOLUME]
        t_total = self.search(Column.VOLUME, v5 + 500)[Column.TIME]
        return t_total - 5*60


    def calc_tf15(self) -> float:
        v15 = self.search(Column.TIME, 15*60)[Column.VOLUME]
        t_total = self.search(Column.VOLUME, v15 + 500)[Column.TIME]
        return t_total - 15*60


    def calc_sdi15(self) -> float:
         return (1 - self.calc_ti() / self.calc_tf15()) * 100 / 15  


    def calc_sdi5(self) -> float:
         return (1 - self.calc_ti() / self.calc_tf5()) * 100 / 5  


    def calc_avg_temp(self) -> float:
        return sum([x[Column.TEMPERATURE] for x in self.data])/len(self.data)


    def calc_mfi(self) -> float:
        v5i, _ = self.search_index(Column.TIME, 5*60)
        v15i, _ = self.search_index(Column.TIME, 15*60)
        x = np.array([x[Column.VOLUME] / 1000 for x in self.data[v5i:v15i + 1]]).reshape((-1,1))
        y = np.array([x[Column.TIME] / (x[Column.VOLUME] / 1000) for x in self.data[v5i:v15i + 1]])

        model = LinearRegression()
        model.fit(x, y)
        r_sq = model.coef_[0]

        return float(r_sq)


def parse(filename : str) -> MembraneFouling:
    with open(filename) as f:
        data = f.read()

    lines = data.strip().split("\n")
    mf = MembraneFouling(*lines[1:7])

    for line in lines[8:]:
        mf.add_data(line)

    return mf


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='Membrane Fouling data processing', description='Calsulate Membrane Fouling metrics')
    parser.add_argument('-f', '--file', required=True, help="csv file to be processed")

    args = parser.parse_args(sys.argv[1:])

    mf = parse(args.file)

    print(mf)
    print(f'ti       : {mf.calc_ti():.3f}')
    print(f'tf5      : {mf.calc_tf5():.3f}')
    print(f'tf15     : {mf.calc_tf15():.3f}')
    print(f'sdi5     : {mf.calc_sdi5():.2f}')
    print(f'sdi15    : {mf.calc_sdi15():.2f}')
    print(f'mfi      : {mf.calc_mfi():.3f}')
    print(f'avg temp : {mf.calc_avg_temp():.3f}')

