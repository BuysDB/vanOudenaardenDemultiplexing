#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob, os, re
from colorama import Fore
from colorama import Back
from colorama import Style

def formatColor(string):
    return(
        string.replace("[GREEN]", Fore.GREEN)
        .replace("[RED]", Fore.RED)
        .replace("[DIM]", Style.DIM)
        .replace("[RESET]", Style.RESET_ALL)
        .replace("[BRIGHT]", Style.BRIGHT)
        .replace("[NORMAL]", Style.NORMAL)
    )
class SequencingLibraryLister():
    def __init__(self):
        pass


    # Function which replaces the substring(s) in library within args.replace
    def libraryReplace(self, library, args):
        if args.replace is None:
            return library

        for k in args.replace:
            origin, replace = k.split(',')
            library = library.replace(origin,replace)
        return library

    def detect(self, filesToList, args):

        if args.replace:
            try:
                print("Library name replacement:" )
                for k in args.replace:
                    origin, replace = k.split(',')
                    print( formatColor("  -> [DIM]looking for[RESET] '%s' [DIM]replace with:[RESET]'%s'" % (origin, replace)))
            except Exception as e:
                print(e)
        self.libraries = {}
        mergeReport = False

        # Glob expansion:
        if any( '*' in path for path in args.fastqfiles ):
            fqfiles = []
            for path in args.fastqfiles:
                fqfiles += list(glob.glob(path))
        else:
            fqfiles =  args.fastqfiles

        for path in fqfiles:
            completefastqFileName = os.path.basename(path)
            fastqFileName = completefastqFileName.replace('.fastq','').replace('.gz','').replace('.fq','')

            # Base Clear format: Organoid-VG-diff_32158_TTAGGCATTCTTTCCC_L001_R2_001_BHGFKLBCX2.filt.fastq.gz
            if fastqFileName.endswith('.filt'):
                fastqFileName = fastqFileName.rsplit('_',1)[0]

            #Check if we are dealing with a raw illumina or SRR fastq file:

            if fastqFileName.endswith('_R1') or fastqFileName.endswith('_R2'):
                lane = '0' # Create "fake" lane
                library = self.libraryReplace(fastqFileName.rsplit('_R',1)[0], args)
                r1ORr2 = fastqFileName.rsplit('_', 1)[-1]

                if not library in self.libraries:
                    self.libraries[library] = {lane: {}}

                if not r1ORr2 in self.libraries[library][lane]:
                    self.libraries[library][lane][r1ORr2] = []

                self.libraries[library][lane][r1ORr2].append( path )
                #print(path, library, r1ORr2, self.libraries)

            elif fastqFileName.startswith("SRR"):

                library,r1ORr2 = fastqFileName.split('_')
                library = self.libraryReplace(library,args)
                r1ORr2 = 'R%s' % r1ORr2 #The demultiplexer expects the format 'R1'
                if args.slib!=None:
                    lane = library
                    library = args.slib
                else:
                    lane = '0'

                if not library in self.libraries:
                    self.libraries[library] = {lane:{}}
                if not lane in self.libraries[library]:
                    self.libraries[library][lane] = {}

                if not r1ORr2 in self.libraries[library][lane]:
                    self.libraries[library][lane][r1ORr2] = []
                self.libraries[library][lane][r1ORr2].append( path )
            else:
                library = self.libraryReplace(re.sub(r'_L[0-9]{3}_R(1|2)_[0-9]{3}', '', fastqFileName),args)
                if args.slib!=None:
                    lane = library
                    library = args.slib

                if args.merge:
                    delim = args.merge[0]
                    nThSplit = int(args.merge[1:]) if len(args.merge)>1 else 1
                    newLibraryName = "".join(library.split(args.merge[0])[:nThSplit])
                    if not mergeReport:
                        #print("Library merger: %sSplitting on '%s%s%s%s', until part %s%s%s, %s %s->%s %s" % (Style.DIM, Style.RESET_ALL, delim, Style.DIM, Style.RESET_ALL,  nThSplit, Style.DIM, Style.RESET_ALL, library, Style.DIM, Style.RESET_ALL, newLibraryName))

                        print( formatColor("Library merger: [DIM]Splitting on '[RESET]%s[DIM]', until part [RESET]%s[DIM], [RESET]%s[DIM] -> [RESET]%s") % (delim, nThSplit, library, newLibraryName))

                        mergeReport=True
                    library = newLibraryName
                if not library in self.libraries:
                    self.libraries[library] = {}
                lane =     re.sub(r'_R(1|2)_[0-9]{3}', '', fastqFileName)
                if not lane in self.libraries[library]:
                    self.libraries[library][lane] = {}
                #Obtaining that it is R1 or R2:
                r1ORr2 = re.sub( r'_[0-9]{3}','', fastqFileName.replace('%s_' % lane,''))

                if not r1ORr2 in self.libraries[library][lane]:
                    self.libraries[library][lane][r1ORr2] = []
                self.libraries[library][lane][r1ORr2].append( path )


        inconsistent = False
        ignoreFiles = []
        for idx,lib in enumerate(sorted(self.libraries)):
            print(('%s%s%s %s' % ('\n' if idx>0 else '', lib, Style.DIM, Style.RESET_ALL)))

            inconsistentLane = False
            for lane in sorted(self.libraries[lib]):
                print(("   %s%s%s" % (Style.DIM,lane,Style.RESET_ALL)))
                if len(self.libraries[lib][lane])!=2:
                    if not args.se:
                        inconsistent = True
                        inconsistentLane = True
                        if args.ignore:
                            ignoreFiles.append( (lib, lane) )
                            print(('%s    %s IGNORED FILE.. BOTH MATES NOT AVAILABLE or no mates? %s' % (Fore.RED, lib, Style.RESET_ALL)))
                        else:
                            print(('%s    %s BOTH MATES NOT AVAILABLE%s' % (Fore.RED, lib, Style.RESET_ALL)))

                prevSize = None
                for R1R2 in sorted(self.libraries[lib][lane]):
                    if prevSize!=None and prevSize!=len(self.libraries[lib][lane][R1R2]):
                        #Missing a mate file
                        inconsistent=True
                        print(("%s    %s %s%s" % (Fore.RED, R1R2, ', '.join(self.libraries[lib][lane][R1R2] ), Style.RESET_ALL)))
                        if args.ignore:
                            ignoreFiles.append( (lib, lane) )
                    else:
                        prevSize = len(self.libraries[lib][lane][R1R2])
                        #Correct library
                        print(("%s    %s %s%s" % (Fore.RED if inconsistentLane else Fore.GREEN, R1R2, ', '.join(self.libraries[lib][lane][R1R2] ), Style.RESET_ALL)))


        if inconsistent:
            if args.ignore:
                print("Mate information missing for some files. --ignore was supplied, ignoring these files:")
                for ignore in ignoreFiles:
                    print("%s %s" % (ignore[0], ignore[1]))
                    del self.libraries[ignore[0]][ignore[1]]
                #Drop empty self.libraries:
                dropLibs = []
                for lib in self.libraries:
                    if len(self.libraries[lib])==0:
                        dropLibs.append(lib)
                for d in list(set(dropLibs)):
                    try:
                        del self.libraries[d]
                    except:
                        pass
            else:
                print(('%sExitting, mate-information missing%s. Supply --se to allow single end reads or --ignore to ignore these files.' % (Fore.RED, Style.RESET_ALL)))
                exit()
        return self.libraries
