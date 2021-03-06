#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import pysam
import collections
import argparse
import pandas as pd
import baseDemultiplexMethods
TagDefinitions = baseDemultiplexMethods.TagDefinitions

argparser = argparse.ArgumentParser(
 formatter_class=argparse.ArgumentDefaultsHelpFormatter,
 description='Tabulate a bam file to a file where every line corresponds to the features of a single read')
argparser.add_argument('-o',  type=str, help="output csv path", required=False)
argparser.add_argument('-featureTags',  type=str, default=None, help='These define the columns of your output matrix. For example if you want sample (SM) allele (DA) and restriction site (DS) use SM,DA,DS. If you want a column containing the chromosome mapped to use "chrom" as feature.')

argparser.add_argument('alignmentfiles',  type=str, nargs='*')
argparser.add_argument('-head',  type=int, help='Run the algorithm only on the first N reads to check if the result looks like what you expect.')
argparser.add_argument('--dedup', action='store_true', help='Count only the first occurence of a molecule. Requires RC tag to be set. Reads without RC tag will be ignored!')
argparser.add_argument('--showtags',action='store_true', help='Show a list of commonly used tags, and tags present in your bam file' )
args = argparser.parse_args()

if args.showtags:
    # Find which tags are available in the file:
    head = 1000
    tagObs = collections.Counter()
    for bamFile in args.alignmentfiles:
        with pysam.AlignmentFile(bamFile) as f:
            for i,read in enumerate(f):
                tagObs += collections.Counter([ k for k,v in   read.get_tags(with_value_type=False)] )
                if i==(head-1):
                    break
    import colorama

    print(f'{colorama.Style.BRIGHT}Tags seen in the supplied bam file(s):{colorama.Style.RESET_ALL}')
    for observedTag in tagObs:
        tag = observedTag
        if observedTag in TagDefinitions:
            t = TagDefinitions[observedTag]
            humanName = t.humanName
            isPhred = t.isPhred
        else:
            t = observedTag
            isPhred = False
            humanName=f'{colorama.Style.RESET_ALL}<No information available>'

        allReadsHaveTag = ( tagObs[tag]==head )
        color = colorama.Fore.GREEN if allReadsHaveTag else colorama.Fore.YELLOW
        print(f'{color}{ colorama.Style.BRIGHT}{tag}{colorama.Style.RESET_ALL}\t{color+humanName}\t{colorama.Style.DIM}{"PHRED" if isPhred else ""}{colorama.Style.RESET_ALL}' + f'\t{"" if allReadsHaveTag else "Not all reads have this tag"}')

    print(f'{colorama.Style.BRIGHT}\nAVO lab tag list:{colorama.Style.RESET_ALL}')
    for tag,t in TagDefinitions.items():
        print(f'{colorama.Style.BRIGHT}{tag}{colorama.Style.RESET_ALL}\t{t.humanName}\t{colorama.Style.DIM}{"PHRED" if t.isPhred else ""}{colorama.Style.RESET_ALL}')
    exit()
if args.o is None:
    raise ValueError('Supply an output file')
if args.alignmentfiles is None:
    raise ValueError('Supply alignment (BAM) files')

if args.featureTags is None:
    raise ValueError('Supply feature tags')

featureTags= args.featureTags.split(',')
countTable = collections.defaultdict(collections.Counter) # cell->feature->count
def tagToHumanName(tag,TagDefinitions ):
    if not tag in TagDefinitions:
        return tag
    return TagDefinitions[tag].humanName

with open(args.o,'w') as tf:
    # Write header:

    tf.write( '\t'.join([tagToHumanName(t, TagDefinitions) for t in featureTags])+'\n' )
    for bamFile in args.alignmentfiles:
        with pysam.AlignmentFile(bamFile) as f:
            for i,read in enumerate(f):
                if args.dedup and ( not read.has_tag('RC') or (read.has_tag('RC') and read.get_tag('RC')!=1)):
                    continue

                tf.write( '%s\n' % '\t'.join([
                    str(read.reference_name) if tag=='chrom' else (str(read.get_tag(tag) if read.has_tag(tag) else 'None'))
                    for tag in featureTags
                ]))
