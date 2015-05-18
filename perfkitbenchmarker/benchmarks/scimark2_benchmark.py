# Copyright 2015 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Contributed by: Zi Shen Lim.

"""Runs SciMark2.

Original documentation & code: http://math.nist.gov/scimark2/

SciMark2 is a Java (and C) benchmark for scientific and numerical computing.
It measures several computational kernels and reports a composite score in
approximate Mflops (Millions of floating point operations per second).

For convenience, we use the code base at https://github.com/zlim/scimark2,
which contains both the Java and C versions of SciMark2 in a single
repository.
"""

import logging
import re

from perfkitbenchmarker import regex_util
from perfkitbenchmarker import sample
from perfkitbenchmarker import vm_util

# Use this directory for all data stored in the VM for this test.
SCIMARK2_PATH = '{0}/scimark2'.format(vm_util.VM_TMP_DIR)

# Download location for both the C and Java tests.
SCIMARK2_BASE_URL = 'http://math.nist.gov/scimark2'

# Java-specific constants.
SCIMARK2_JAVA_JAR = 'scimark2lib.jar'
SCIMARK2_JAVA_MAIN = 'jnt.scimark2.commandline'

# C-specific constants.
SCIMARK2_C_ZIP = 'scimark2_1c.zip'
SCIMARK2_C_SRC = '{0}/src'.format(SCIMARK2_PATH)
# SciMark2 does not set optimization flags, it leaves this to the
# discretion of the tester. The following gets good performance and
# has been used for LLVM and GCC regression testing, see for example
# https://llvm.org/bugs/show_bug.cgi?id=22589 .
SCIMARK2_C_CFLAGS = '-O3 -march=native'

BENCHMARK_INFO = {'name': 'scimark2',
                  'description': 'Runs SciMark2',
                  'scratch_disk': False,
                  'num_machines': 1}


def GetInfo():
  return BENCHMARK_INFO


def CheckPrerequisites():
  pass


def Prepare(benchmark_spec):
  """Install SciMark2 on the target vm.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """
  vms = benchmark_spec.vms
  vm = vms[0]
  logging.info('Preparing SciMark2 on %s', vm)
  vm.Install('build_tools')
  vm.Install('wget')
  vm.Install('openjdk7')
  vm.InstallPackages('unzip')
  cmds = [
      'rm -rf {0} && mkdir {0}'.format(SCIMARK2_PATH),
      'wget {0}/{1} -O {2}/{1}'.format(
          SCIMARK2_BASE_URL, SCIMARK2_JAVA_JAR, SCIMARK2_PATH),
      'wget {0}/{1} -O {2}/{1}'.format(
          SCIMARK2_BASE_URL, SCIMARK2_C_ZIP, SCIMARK2_PATH),
      '(mkdir {0} && cd {0} && unzip {1}/{2})'.format(
          SCIMARK2_C_SRC, SCIMARK2_PATH, SCIMARK2_C_ZIP),
      '(cd {0} && make CFLAGS="{1}")'.format(
          SCIMARK2_C_SRC, SCIMARK2_C_CFLAGS)
  ]
  for cmd in cmds:
    vm.RemoteCommand(cmd, should_log=True)


def Run(benchmark_spec):
  """Run SciMark2 on the target vm.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.

  Returns:
    A list of sample.Sample objects.
  """
  vms = benchmark_spec.vms
  vm = vms[0]
  logging.info('Running SciMark2 on %s', vm)
  samples = []
  # Run the Java and C benchmarks twice each, once with defaults and
  # once with the "-large" flag to use a larger working set size.
  #
  # Since the default output is not very parsing-friendly, print an
  # extra header to identify the tests. This must match
  # RESULT_START_REGEX as used below.
  cmds = [
      '(echo ";;; Java small"; cd {0} && java -cp {1} {2})'.format(
          SCIMARK2_PATH, SCIMARK2_JAVA_JAR, SCIMARK2_JAVA_MAIN),
      '(echo ";;; C small"; cd {0} && ./scimark2)'.format(
          SCIMARK2_C_SRC),
      '(echo ";;; Java large"; cd {0} && java -cp {1} {2} -large)'.format(
          SCIMARK2_PATH, SCIMARK2_JAVA_JAR, SCIMARK2_JAVA_MAIN),
      '(echo ";;; C large"; cd {0} && ./scimark2 -large)'.format(
          SCIMARK2_C_SRC),
  ]
  for cmd in cmds:
    stdout, _ = vm.RemoteCommand(cmd, should_log=True)
    samples.extend(ParseResults(stdout))
  return samples


def Cleanup(benchmark_spec):
  """Cleanup SciMark2 on the target vm.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """
  pass


def ParseResults(results):
  """Result parser for SciMark2.

  Sample Results (C version):
    **                                                              **
    ** SciMark2 Numeric Benchmark, see http://math.nist.gov/scimark **
    ** for details. (Results can be submitted to pozo@nist.gov)     **
    **                                                              **
    Using       2.00 seconds min time per kenel.
    Composite Score:         1596.04
    FFT             Mflops:  1568.64    (N=1024)
    SOR             Mflops:  1039.98    (100 x 100)
    MonteCarlo:     Mflops:   497.64
    Sparse matmult  Mflops:  1974.39    (N=1000, nz=5000)
    LU              Mflops:  2899.56    (M=100, N=100)

  (Yes, "kenel" is part of the original output.)

  Sample Results (Java version):

    SciMark 2.0a

    Composite Score: 1731.4467627163242
    FFT (1024): 996.9938397943672
    SOR (100x100):   1333.5328291027124
    Monte Carlo : 724.5221517116782
    Sparse matmult (N=1000, nz=5000): 1488.18620413327
    LU (100x100): 4113.998788839592

    java.vendor: Oracle Corporation
    java.version: 1.7.0_75
    os.arch: amd64
    os.name: Linux
    os.version: 3.16.0-25-generic

  Args:
    results: SciMark2 result.

  Returns:
    A list of sample.Sample objects.
  """
  RESULT_START_REGEX = re.compile(r'^;;; \s+ (.*)', re.X | re.M)

  SCORE_REGEX = re.compile(r'''
    ^ (Composite \s+ Score) : \s+ (\d+ \. \d+)
  ''', re.X | re.M)
  RESULT_REGEX_C = re.compile(r'''
    ^
    ( .+? ) \s+  #1: Test name
    Mflops: \s+
    ( \d+ \. \d+ )  #2: Test score
    ( \s+ \( .+? \) )?  #3: Optional test details
  ''', re.X | re.M)
  RESULT_REGEX_JAVA = re.compile(r'''
    ^
    ( .+? )  #1: Test name
    : \s+
    ( \d+ \. \d+ )  #2: Test score
  ''', re.X | re.M)
  PLATFORM_REGEX = re.compile(r'''
    ^
    ( \w+ \. \w+ )  #1: Property name
    : \s+
    ( .* )  #2: Property value
  ''', re.X | re.M)

  def FindBenchStart(results, start_index=0):
    m = RESULT_START_REGEX.search(results, start_index)
    if m is None:
      return -1, 'Unknown'
    return m.start(), m.group(1)

  def ExtractPlatform(result, bench_version):
    metadata = {}
    meta_start = None
    if bench_version.startswith('C'):
      pass
    elif bench_version.startswith('Java'):
      for m in PLATFORM_REGEX.finditer(result):
        if meta_start is None:
          meta_start = m.start()
        metadata[m.group(1)] = m.group(2)
    return metadata, meta_start

  def ExtractScore(result, bench_version):
    m = SCORE_REGEX.search(result)
    label = m.group(1)
    score = float(m.group(2))
    return score, label, m.end()

  def ExtractResults(result, bench_version):
    datapoints = []
    if bench_version.startswith('C'):
      for groups in regex_util.ExtractAllMatches(RESULT_REGEX_C, result):
        metric = '{0} {1}'.format(groups[0].strip(), groups[2].strip())
        metric = metric.strip().strip(':')  # Extra ':' in 'MonteCarlo:'.
        value = float(groups[1])
        datapoints.append((metric, value))
    elif bench_version.startswith('Java'):
      for groups in regex_util.ExtractAllMatches(RESULT_REGEX_JAVA, result):
        datapoints.append((groups[0].strip(), float(groups[1])))
    return datapoints

  # Find start positions for all the test results.
  tests = []
  test_start_pos = 0
  while True:
    start_index, bench_version = FindBenchStart(results, test_start_pos)
    if start_index == -1:
      break
    tests.append((start_index, bench_version))
    test_start_pos = start_index + 1

  # Now loop over individual tests collecting samples.
  samples = []
  for test_num, (start_index, bench_version) in enumerate(tests):
    # Get end index - either start of next test, or None for the last test.
    end_index = None
    if test_num + 1 < len(tests):
      end_index = tests[test_num + 1][0]
    result = results[start_index:end_index]

    metadata = {'bench_version': bench_version}

    # Assume that the result consists of overall score followed by
    # specific scores and then platform metadata.

    # Get the metadata first since we need that to annotate samples.
    platform_metadata, meta_start = ExtractPlatform(result, bench_version)
    metadata.update(platform_metadata)

    # Get the overall score.
    score, label, score_end = ExtractScore(result, bench_version)
    samples.append(sample.Sample(label, score, 'Mflops', metadata))

    # For the specific scores, only look at the part of the string
    # bounded by score_end and meta_start to avoid adding extraneous
    # items. The overall score and platform data would match the
    # result regex.
    datapoints = ExtractResults(result[score_end:meta_start], bench_version)
    for metric, value in datapoints:
      samples.append(sample.Sample(metric, value, 'Mflops', metadata))

  return samples
