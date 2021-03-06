#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import re
import gzip
from colorama import Fore
from colorama import Back
from colorama import Style
import argparse
import barcodeFileParser
import sequencingLibraryListing
import importlib
import inspect
import traceback
import collections
import fastqIterator
import glob
from colorama import init
from baseDemultiplexMethods import NonMultiplexable,IlluminaBaseDemultiplexer
import demultiplexModules
init()
import logging
logging.getLogger().setLevel(logging.WARNING)
#logging.getLogger().setLevel(logging.INFO)

argparser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description="""%sMulti-library Single cell-demultiplexing%s, written by Buys de Barbanson, Hubrecht institute 2016-2018
									%sExample usage:%s

									List how the demultiplexer will interpret the data: (No demultiplexing is executed)
									%sdemultiplex.py ./*.fastq.gz%s
									Demultiplex a set of fastq files into separate files per cell:
									%sdemultiplex.py ./*.fastq.gz --y%s
									Demultiplex on the cluster:
									%sdemultiplex.py ./*.fastq.gz -submit demux.sh; sh demux.sh %s
	"""% (Style.BRIGHT, Style.RESET_ALL, Style.BRIGHT, Style.RESET_ALL, Style.DIM, Style.RESET_ALL, Style.DIM, Style.RESET_ALL, Style.DIM, Style.RESET_ALL))

argparser.add_argument('fastqfiles', metavar='fastqfile', type=str, nargs='*', help='Input fastq files. For windows compatibility, if any of the file names contains a star the expression is evaluated as GLOB. Read names should be in illumina format or LIBRARY_R1.fastq.gz, LIBRARY_R2.fastq.gz, if one file is supplied and the name does not end on .fastq. or fastq.gz the file is interpreted as a list of files')
argparser.add_argument('--y', help="Perform the demultiplexing (Accept current parameters)", action='store_true' )
argparser.add_argument('-experimentName', '-e', help="Name of the experiment, set to uf to use the folder name", type=str, default='uf' )

inputArgs = argparser.add_argument_group('Input', '')
inputArgs.add_argument('-n', help="Only get the first n properly demultiplexable reads from a library", type=int)
inputArgs.add_argument('-r', help="Only get the first n reads from a library, then demultiplex", type=int)
inputArgs.add_argument('-slib', help="Assume all files belong to the same library, this flag supplies the name", type=str )
inputArgs.add_argument('-replace', action='append', default=None, help="""Replace part of the library name by another string, [SEARCH,REPLACEMENT]. For example if you want to remove FOO from the library name use "-replace FOO," if you want to replace FOO by BAR use "-replace FOO,BAR" """)

inputArgs.add_argument('-merge', default=None, help="""Merge libraries through multiple runs by selecting a merging method.
Options:None, delimiter[position], examples, given the samplename 'library_a_b': -merge _ yields 'library', -merge _2 yields 'library_a'as identifier.""")
inputArgs.add_argument('--ignore', action='store_true', help="Ignore non-demultiplexable read files")
#inputArgs.add_argument('-bfsp', help="Barcode file searchpaths", type=str, default='/media/sf_data/references,/hpc/hub_oudenaarden/bdebarbanson/ref')
outputArgs = argparser.add_argument_group('Output', '')
argparser.add_argument('--norejects', help="Do not store rejected reads",  action='store_true')

outputArgs.add_argument('-o', help="Output (cell) file directory, when not supplied the current directory/raw_demultiplexed is used", type=str, default='./raw_demultiplexed')

#outputArgs.add_argument('--nosepf', help="If this flag is not set every cell gets a separate FQ file, otherwise all cells are put in the same file", action='store_true' )
#outputArgs.add_argument('--nogz', help="Output files are not gzipped", action='store_true' )
#outputArgs.add_argument('-submit', default=None, type=str, help="Create cluster submission file")

#bcArgs.add_argument('-d', help="Demultiplexing method. 0: Autodetect cs1 cs2, 1: CelSeq1, 2: Celseq2, 3: DropSeq with R2 barcodes supplied,9: nla384.bc, 100:Lennart virus 1, 900:Bulk: 20: 20:maya_mspj1.bc, There are no barcodes and UMI's, perform only concatenation", type=int, default=0)
bcArgs = argparser.add_argument_group('Barcode', '')
bcArgs.add_argument('-hd', help="Hamming distance barcode expansion; accept cells with barcodes N distances away from the provided barcodes. Collisions are dealt with automatically. ", type=int, default=0)
bcArgs.add_argument('--lbi', help="Summarize the barcodes being used for cell demultuplexing and sequencing indices.", action='store_true')
bcArgs.add_argument('-barcodeDir', default='barcodes', help="Directory from which to obtain the barcodes")

bcArgs = argparser.add_argument_group('Index', '')
bcArgs.add_argument('-hdi', help="Hamming distance INDEX sequence expansion, the hamming distance used for resolving the sequencing INDEX. For cell barcode hamming distance see -hd", type=int, default=1)
#bcArgs.add_argument('-indexAlias', help="Select which indices are used for demultiplexing", type=int, default='')


fragArgs = argparser.add_argument_group('Fragment configuration', '')
#fragArgs.add_argument('--rc1', help="First mate is reverse complemented", action='store_true')
#fragArgs.add_argument('--rc2', help="Second mate is reverse complemented", action='store_true')
fragArgs.add_argument('--se', help="Allow single end reads",  action='store_true')

techArgs = argparser.add_argument_group('Technical', '')
#techArgs.add_argument('-t', help="Amount of demultiplexing threads used" , type=int, default=8)
#techArgs.add_argument('-fh', help="When demultiplexing to mutliple cell files in multiple threads, the amount of opened files can exceed the limit imposed by your operating system. The amount of open handles per thread is kept below this parameter to prevent this from happening.", default=32, type=int)
techArgs.add_argument('-dsize', help="Amount of reads used to determine barcode type" , type=int, default=10000)

argparser.add_argument('-use',default=None, help='use these demultplexing strategies, comma separate to select multiple. For example for cellseq 2 data with 6 basepair umi: -use CS2C8U6 , for combined mspji and Celseq2: MSPJIC8U3,CS2C8U6 if nothing is specified, the best scoring method is selected' )


argparser.add_argument('-ignoreMethods', help='Do not try to load these methods', default="restriction-bisulfite,scarsMiSeq"  )

argparser.add_argument('-maxAutoDetectMethods','-mxa', help='When --use is not specified, how many methods can the demultiplexer choose at the same time? This loosely corresponds to the amount of measurements you made in a single cell', default=1, type=int  )
argparser.add_argument('-minAutoDetectPct','-mia', help='When --use is not specified, what is the lowest percentage yield required to select a demultplexing strategy', default=2, type=float  )
args = argparser.parse_args()
verbosity = 1

ignoreMethods = args.ignoreMethods.split(',')

if len(set(args.fastqfiles))!=len(args.fastqfiles):
	print(f'{Fore.RED}{Style.BRIGHT}Some fastq files are supplied multiple times! Pruning those!{Style.RESET_ALL}')
	args.fastqfiles = set(args.fastqfiles)

if len(args.fastqfiles)==1:
	if not args.fastqfiles[0].endswith('.gz') and not args.fastqfiles[0].endswith('.fastq')  and not args.fastqfiles[0].endswith('.fq'):
		# File list:
		print('Input is interpreted as a list of files..')
		with open(args.fastqfiles[0]) as f:
			fqFiles = []
			for line in f:
				fqFiles.append( line.strip() )
		args.fastqfiles = fqFiles



class FastqHandle:

	def __init__(self, path, pairedEnd=False ):
		self.pe = pairedEnd
		if pairedEnd:
			self.handles = [ gzip.open(path+'R1.fastq.gz', 'wt'),   gzip.open(path+'R2.fastq.gz', 'wt') ]
		else:
			self.handles = [ gzip.open(path+'reads.fastq.gz', 'wt') ]


	def write(self, records ):
		for handle, record in zip(self.handles, records):
			handle.write(record)


# Load barcodes
barcodeParser = barcodeFileParser.BarcodeParser(hammingDistanceExpansion=args.hd, barcodeDirectory=args.barcodeDir)

indexParser =  barcodeFileParser.BarcodeParser(hammingDistanceExpansion=args.hdi, barcodeDirectory='indices')
if args.lbi:
	barcodeParser.list()
	indexParser.list()

# Load strategies from the demultiplexModules folder
class DemultiplexingStrategyLoader:
	def __init__(self, barcodeParser, moduleSearchDir= './demultiplexModules', indexParser=None, ignoreMethods=None):
		package = moduleSearchDir.split('/')[-1]
		moduleSearchPath = os.path.join( os.path.dirname(os.path.realpath(__file__)), moduleSearchDir)
		self.barcodeParser = barcodeParser
		self.indexParser = indexParser
		moduleSearchPath = moduleSearchPath
		print(f'{Style.DIM}Current script location: {__file__}')
		print(f'Searchdir: {moduleSearchDir}')
		print(f'Looking for modules in {moduleSearchPath}{Style.RESET_ALL}')
		self.demultiplexingStrategies = []
		for modulePath in glob.glob(f'{moduleSearchPath}/*.py'):

			try:
				module = (modulePath.split('/')[-1].replace('.py',''))
				if ignoreMethods is not None and module in ignoreMethods:
					print(f"{Style.DIM}Ignoring demultiplex method {module}, use -ignoreMethods none to re-enable{Style.RESET_ALL}")
					continue
				if module=='__init__':
					continue
 #modulePath.replace('\\','/').replace('/','.').replace('..','').replace('.py','').lstrip('.').split('.')[-1]

				loadedModule = importlib.import_module(f'.{module}', package)
				# Only obtain classes defined in the module, not imported ones:
				is_class_member = lambda member: inspect.isclass(member) and member.__module__ == f'{package}.{module}'
				for className, classDetails in inspect.getmembers(sys.modules[f'{package}.{module}'], is_class_member):
					# Obtain a handle to the class and instatiate the strategy
					class_ = getattr(loadedModule, className)
					initiatedDemultiplexingStrategy = class_( barcodeFileParser=barcodeParser, indexFileParser=indexParser)
					self.demultiplexingStrategies.append(initiatedDemultiplexingStrategy)
					#print(initiatedDemultiplexingStrategy.name)

			except Exception as e:

				print(f"{Fore.RED}{Style.BRIGHT}FAILED LOADING {module} at {modulePath}\nException: {e}{Style.RESET_ALL}\nTraceback for the error:\n")
				import traceback
				traceback.print_exc()

				from os import stat
				from pwd import getpwuid

				print(f'Contact {Style.BRIGHT}%s{Style.RESET_ALL} for help\n' % getpwuid(stat(modulePath).st_uid).pw_name)
				print('The error only affects this module.\nProceeding to load more modules...\n')

	def getSelectedStrategiesFromStringList(self, strList):
		selectedStrategies = []

		resolved = {part:False for part in strList}
		for strategy in self.demultiplexingStrategies:
			if strategy.shortName in strList:
				selectedStrategies.append(strategy)
				print('Selected strategy %s' % strategy)
				resolved[strategy.shortName] = True


		if any( [v is False for v in resolved.values()]):
			for strat in strList:
				if resolved[strat] is False:
					print(f'{Fore.RED}Could not resolve {strat}{Style.RESET_ALL}')
					print('Available:')
					for s in self.demultiplexingStrategies:
						print(s.shortName)
					raise ValueError(f'Strategy {strat} not found')

			raise ValueError()
		return selectedStrategies

	def list(self):
		print(f"{Style.BRIGHT}Available demultiplexing strategies:{Style.RESET_ALL}")
		#print('Name, alias, will be auto detected, description')
		for strategy in self.demultiplexingStrategies:

			try:
				print(f'{Style.BRIGHT}{strategy.shortName}{Style.RESET_ALL}\t{strategy.longName}\t' + (f'{Fore.GREEN}Will be autodetected' if strategy.autoDetectable else f'{Fore.RED}Will not be autodetected')+Style.RESET_ALL + Style.DIM + f' {strategy.barcodeFileParser.getTargetCount(strategy.barcodeFileAlias) if strategy.barcodeFileParser is not None else "NA"} targets\n '+ Style.DIM + strategy.description +'\n'+strategy.getParserSummary() + Style.RESET_ALL +'\n' )
			except Exception as e:
				print(f"{Fore.RED}{Style.BRIGHT}Error in: {strategy.shortName}\nException: {e}{Style.RESET_ALL}\nTraceback for the error:\n")
				import traceback
				traceback.print_exc()
				from os import stat
				from pwd import getpwuid
				try:
					modulePath = sys.modules[strategy.__module__].__file__

					print(f'Contact {Style.BRIGHT}%s{Style.RESET_ALL} for help\n' % getpwuid(stat(modulePath).st_uid).pw_name)
					print('The error only affects this module.\nProceeding to load more modules...\n')
				except Exception as e:
					pass

	def getAutodetectStrategies(self):
		return [strategy for strategy in self.demultiplexingStrategies if  strategy.autoDetectable ]

	def getDemultiplexingSelectedStrategies(self):
		if self.selectedStrategies is None:
			raise ValueError('No strategies selected')
		return self.selectedStrategies

	def demultiplex(self, fastqfiles, maxReadPairs=None, strategies=None, library=None, targetFile=None, rejectHandle=None):

		useStrategies = strategies if strategies is not None else self.getAutodetectStrategies()
		strategyYields = collections.Counter()
		processedReadPairs=0
		baseDemux = IlluminaBaseDemultiplexer(indexFileParser=self.indexParser, barcodeParser=self.barcodeParser)

		for processedReadPairs, reads in enumerate(fastqIterator.FastqIterator(*fastqfiles)):
			for strategy in useStrategies:
				try:

					recodedRecords = strategy.demultiplex(reads, library=library)

					if targetFile is not None:
						targetFile.write( recodedRecords )

				except NonMultiplexable:
					#print('NonMultiplexable')

					if rejectHandle is not None:
						try:
							rejectHandle.write( baseDemux.demultiplex(reads, library=library) )
						except NonMultiplexable as e:
							print(e)

					continue
				except Exception as e:
					print( traceback.format_exc() )
					print(f'{Fore.RED}Fatal error. While demultiplexing strategy {strategy.longName} yielded an error, the error message was: {e}')
					print('The read(s) causing the error looked like this:')
					for read in reads:
						print(str(read))
					print(Style.RESET_ALL)
				#print(recodedRecord)
				strategyYields[strategy.shortName]+=1
			if ( maxReadPairs is not None and (1+processedReadPairs)>=maxReadPairs):
				break
		return processedReadPairs+1,strategyYields



	def detectLibYields(self, libraries, strategies=None, testReads=100000,maxAutoDetectMethods=1,minAutoDetectPct=5):
		libYields = dict()

		for lib, lanes in libraries.items():
			for lane, readPairs in lanes.items():

				for readPair in readPairs:
					if len(readPairs)==1:
						processedReadPairs, strategyYields = self.demultiplex( [readPairs['R1'][0]],maxReadPairs=testReads,strategies=strategies  )
					elif len(readPairs)==2:
						processedReadPairs, strategyYields  =  self.demultiplex( (readPairs['R1'][0], readPairs['R2'][0] ),maxReadPairs=testReads,strategies=strategies  )
					else:
						raise ValueError('Error: %s' % readPairs.keys())

				print(f'Report for {lib}:')
				self.strategyYieldsToFormattedReport( processedReadPairs, strategyYields,maxAutoDetectMethods=maxAutoDetectMethods,minAutoDetectPct=minAutoDetectPct)
				libYields[lib]= {'processedReadPairs':processedReadPairs, 'strategyYields':strategyYields }
				break
		return processedReadPairs, libYields

	def strategyYieldsToFormattedReport(self, processedReadPairs, strategyYields, selectedStrategies=None,maxAutoDetectMethods=1,minAutoDetectPct=5):
		print(f'Analysed {Style.BRIGHT}{processedReadPairs}{Style.RESET_ALL} read pairs')

		if selectedStrategies is None:
			selectedStrategies = {}
		#selectedStrategies = self.selectedStrategiesBasedOnYield(processedReadPairs, strategyYields)
		for i,(strategy, strategyYield) in enumerate(strategyYields.most_common()):
			yieldRatio = strategyYield/(0.001+processedReadPairs)
			print( ( Style.BRIGHT+Fore.GREEN if ((strategy in selectedStrategies) or i<maxAutoDetectMethods) else (Fore.YELLOW if yieldRatio*100>=minAutoDetectPct else Style.DIM)) +  f'\t {strategy}:%.2f%%{Style.RESET_ALL}'% (100.0*yieldRatio))

	def selectedStrategiesBasedOnYield(self, processedReadPairs, strategyYields, maxAutoDetectMethods=1, minAutoDetectPct=0.05):
		selectedStrategies = []
		for strategy, strategyYield in strategyYields.most_common(maxAutoDetectMethods):
			yieldRatio = strategyYield/(0.001+processedReadPairs)*100.0
			if yieldRatio>=minAutoDetectPct:
				selectedStrategies.append(strategy)
		return selectedStrategies

#Load the demultiplexing strategies
dmx = DemultiplexingStrategyLoader(barcodeParser=barcodeParser, indexParser=indexParser,ignoreMethods=ignoreMethods)
dmx.list()

if len(args.fastqfiles)==0:
	print(f'{Fore.RED}No files supplied, exitting.{Style.RESET_ALL}')
	exit()

print(f"\n{Style.BRIGHT}Detected libraries:{Style.RESET_ALL}")
libraries = sequencingLibraryListing.SequencingLibraryLister().detect(args.fastqfiles, args)

# Detect the libraries:
if args.use is None:
	if len(libraries)==0:
		raise ValueError('No libraries found')

	print(f"\n{Style.BRIGHT}Demultiplexing method Autodetect results{Style.RESET_ALL}")
	# Run autodetect
	processedReadPairs, strategyYieldsForAllLibraries = dmx.detectLibYields(libraries, testReads=args.dsize, maxAutoDetectMethods=args.maxAutoDetectMethods, minAutoDetectPct=args.minAutoDetectPct)

print(f"\n{Style.BRIGHT}Demultiplexing:{Style.RESET_ALL}")
for library in libraries:
	if args.use is None:
		processedReadPairs = strategyYieldsForAllLibraries[library]['processedReadPairs']
		strategyYieldForLibrary =  strategyYieldsForAllLibraries[library]['strategyYields']
		selectedStrategies = dmx.selectedStrategiesBasedOnYield(processedReadPairs, strategyYieldForLibrary, maxAutoDetectMethods = args.maxAutoDetectMethods, minAutoDetectPct=args.minAutoDetectPct)
		selectedStrategies = dmx.getSelectedStrategiesFromStringList(selectedStrategies)
	else:
		selectedStrategies = dmx.getSelectedStrategiesFromStringList(args.use.split(','))

	print(f'Library {library} will be demultiplexed using:')
	for stra in selectedStrategies:
		print(f'\t{Fore.GREEN}{str(stra)}{Style.RESET_ALL}')
	if len(selectedStrategies)==0:
		print(f'{Fore.RED}NONE! The library will not be demultiplexed!{Style.RESET_ALL}')

	if not args.y:
		#with open(args.submit, 'w') as f:

		filesForLib = []
		for lane in libraries[library]:
			for R1R2 in libraries[library][lane]:
				for p in libraries[library][lane][R1R2]:
					filesForLib.append( p )
		arguments = " ".join([x for x in sys.argv if x!='--dry' and not '--y' in x and not '-submit' in x and not '.fastq' in x and not '.fq' in x]) + " --y"

		print(f"\n{Style.BRIGHT}--y not supplied, execute the command below to run demultiplexing on the cluster:{Style.RESET_ALL}")
		print( os.path.dirname(os.path.abspath(__file__)) + '/../submission.py' + f' -y --nenv -time 50 -t 1 -m 8 -N NDMX%s "source /hpc/hub_oudenaarden/bdebarbanson/virtualEnvironments/py36/bin/activate; %s -use {",".join([x.shortName for x in selectedStrategies])}"\n' % (library, '%s %s'  % ( arguments, " ".join(filesForLib)) ))

	if args.y:
		targetDir = f'{args.o}/{library}'
		if not os.path.exists(targetDir):
			os.makedirs(targetDir)
		handle = FastqHandle(f'{args.o}/{library}/demultiplexed' , True)

		rejectHandle = FastqHandle(f'{args.o}/{library}/rejects' , True)

		processedReadPairsForThisLib = 0

		for lane, readPairs in libraries[library].items():
			if args.n and processedReadPairsForThisLib>=args.n:
				break
			for readPair in readPairs:
				pass
			for readPairIdx,_ in enumerate(readPairs[readPair]):
				files = [ readPairs[readPair][readPairIdx] for readPair in readPairs ]
				processedReadPairs,strategyYields = dmx.demultiplex( files , strategies=selectedStrategies, targetFile=handle, rejectHandle=rejectHandle,
				library=library, maxReadPairs=None if args.n is None else (args.n-processedReadPairsForThisLib))
				processedReadPairsForThisLib += processedReadPairs
				if args.n and processedReadPairsForThisLib>=args.n:
					break
