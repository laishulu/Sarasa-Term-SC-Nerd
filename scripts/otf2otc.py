# otf2otc.py v1.5 October 12 2017

__copyright__ = """Copyright 2014,2017 Adobe Systems Incorporated (http://www.adobe.com/). All Rights Reserved.
"""

__help__ = """
otf2otc  -t <table tag=src font index> -o <output ttc file name> <input font file 0> ... <input font file n>

-t <table tag=source font index>  Optional. When this option is present, the matching table from the specified font file is
used for all the font files.

example:
  otf2otc -t 'CFF '=2 -o LogoCutStd.ttc LogoCutStd-Light.otf LogoCutStd-Medium.otf LogoCutStd-Bold.otf LogoCutStd-Ultra.otf
# The 'ttc' file will contain only one CFF table, taken from  LogoCutStd-Bold.otf.

The script mbe invoked with either the FDK command:
  otf2otc
or directly with the command:
  python <path to FDK directory>/python/afdko/otf2otc.py

Build an OpenType Collection font file from two or more OpenType font
files. The fonts are ordered in the output 'ttc' file in the same order
that the file names are listed in the command line. If a table is
identical for more than one font file, it is shared.

"""

__methods__="""
For each file, check that it looks like an sfnt or ttc file.

For each file, read in tables. Build a font object list, and dict of table tags to table data blocks.

A font object contains;
 font file name
 list of [tableTag, table data, shared] pairs
 
as the font tables are being read in, they are compared against the list of already seen data items.
If any match, the font table reference is replaced by the reference to the tabel already seen.
"""

import sys
import os
import struct

class OTCError(TypeError):
	pass

class FontEntry:

	def __init__(self, sfntType, searchRange, entrySelector, rangeShift):
		self.sfntType = sfntType
		self.searchRange = searchRange
		self.entrySelector = entrySelector
		self.rangeShift = rangeShift
		self.tableList = []
		
	def append(self, tableEntry):
		self.tableList.append(tableEntry)
		
	def getTable(self, tableTag):
		for tableEntry in self.tableList:
			if tableTag == tableEntry.tag:
				return tableEntry
		raise KeyError("Failed to find tag: " + tableTag)

	def __str__(self):
		dl = [ "fontEntry sfntType: %s, numTables: %s." % (self.sfntType, len(self.tableList) )]
		for table in self.tableList:
			dl.append(str(table))
		dl.append("")
		return os.linesep.join(dl)
	def __repr__(self):
		return str(self)

class TableEntry:
	
	def __init__(self, tag, checkSum, length):
		self.tag = tag
		self.checksum = checkSum
		self.length = length
		self.data = None
		self.offset = None
		self.isPreferred = False
		
	def __str__(self):
		return "Table tag: %s, checksum: %s, length %s." % (self.tag, self.checksum, self.length )
	def __repr__(self):
		return str(self)
		

ttcHeaderFormat = ">4sLL"
"""
		> # big endian
		TTCTag:                  4s # "ttcf"
		Version:                 L  # 0x00010000 or 0x00020000
		numFonts:                L  # number of fonts
		# OffsetTable[numFonts]: L  # array with offsets from beginning of file
		# ulDsigTag:             L  # version 2.0 only
		# ulDsigLength:          L  # version 2.0 only
		# ulDsigOffset:          L  # version 2.0 only
"""

ttcHeaderSize = struct.calcsize(ttcHeaderFormat)

offsetFormat = ">L"
offsetSize = struct.calcsize(">L")

sfntDirectoryFormat = ">4sHHHH"
"""
		> # big endian
		sfntVersion:    4s
		numTables:      H    # number of tables
		searchRange:    H    # (max2 <= numTables)*16
		entrySelector:  H    # log2(max2 <= numTables)
		rangeShift:     H    # numTables*16-searchRange
"""

sfntDirectorySize = struct.calcsize(sfntDirectoryFormat)

sfntDirectoryEntryFormat = ">4sLLL"
"""
		> # big endian
		tag:            4s
		checkSum:       L
		offset:         L
		length:         L
"""

sfntDirectoryEntrySize = struct.calcsize(sfntDirectoryEntryFormat)

		
def parseArgs(args):
	tagOverrideMap = {}
	ttcFilePath = "TempTTC.ttc"
	fontList = []
	argn = len(args)
	i = 0
	while i < argn:
		arg  = args[i]
		i += 1
		
		if arg[0] != '-':
			fontList.append(arg)
		elif arg == "-o":
			ttcFilePath = args[i]
			i += 1
		elif arg == "-t":
			parts = args[i].split("=")
			try:
				tag = parts[0]
				tag.strip("\"")
				tag.strip("'")
				fontIndex = int(parts[1])
			except (ValueError, IndexError) as e:
				raise OTCError("Badly formed table override." + __help__)
			tagOverrideMap[bytes(tag, 'ascii')] = fontIndex
			i += 1
		elif (arg == "-u") or (arg == "-h"):
			print(__help__)
			raise OTCError()
		else:
			raise OTCError("Unknown option '%s'." % (arg))
			
	if len(fontList) < 1:
		raise OTCError("You must specify at least one input font.")
	
	allOK = True
	for fontPath in fontList:
		if not os.path.exists(fontPath):
			raise OTCError("Cannot find '%s'." % (fontPath))
			
		with open(fontPath, "rb") as fp:
			data = fp.read(4)
		
		if data not in [b"OTTO", b"\0\1\0\0", b"true", b'ttcf']:
			print("File is not OpenType: '%s'." % (fontPath))
			allOK = False
	if not allOK:
		raise OTCError()
	
	return tagOverrideMap, fontList, ttcFilePath

def readFontFile(fontPath):
	fontEntryList = []
	with open(fontPath, "rb") as fp:
		data = fp.read()
	
	# See if this is a OTC file first.
	TTCTag, version, numFonts = struct.unpack(ttcHeaderFormat, data[:ttcHeaderSize])
	if TTCTag != b'ttcf':
		# it is a regular font.
		fontEntry = parseFontFile(0, data)
		fontEntryList.append(fontEntry)
	else:
		offsetdata = data[ttcHeaderSize:]
		i = 0
		while i < numFonts:
			offset = struct.unpack(offsetFormat, offsetdata[:offsetSize])[0]
			fontEntry = parseFontFile(offset, data)
			fontEntryList.append(fontEntry)
			offsetdata = offsetdata[offsetSize:]
			i += 1
	return fontEntryList
	
	
def parseFontFile(offset, data):
	sfntType, numTables, searchRange, entrySelector, rangeShift = struct.unpack(sfntDirectoryFormat, data[offset:offset+sfntDirectorySize])
	fontEntry = FontEntry(sfntType, searchRange, entrySelector, rangeShift)
	curData = data[offset+sfntDirectorySize:]

	i = 0
	while i < numTables:
		tag, checkSum, offset, length = struct.unpack(sfntDirectoryEntryFormat, curData[:sfntDirectoryEntrySize])
		tableEntry = TableEntry(tag, checkSum, length)
		tableEntry.data = data[offset:offset+length]
		fontEntry.append(tableEntry)
		curData =  curData[sfntDirectoryEntrySize:]
		i += 1
	return fontEntry


def writeTTC(fontList, tableList, ttcFilePath):
	numFonts = len(fontList)
	header = struct.pack(ttcHeaderFormat, b'ttcf', 0x00010000,  numFonts)
	dataList = [header]
	fontOffset = ttcHeaderSize + numFonts*struct.calcsize(">L")
	for fontEntry in fontList:
		dataList.append(struct.pack(">L",fontOffset))
		fontOffset += sfntDirectorySize + len(fontEntry.tableList)*sfntDirectoryEntrySize

	# Set the offsets in the tables.
	for tableEntryList in tableList:
		for tableEntry in tableEntryList:
			tableEntry.offset = fontOffset
			paddedLength = (tableEntry.length + 3) & ~3
			fontOffset += paddedLength
			
	# save the font sfnt directories
	for fontEntry in fontList:
		data = struct.pack(sfntDirectoryFormat, fontEntry.sfntType, len(fontEntry.tableList), fontEntry.searchRange, fontEntry.entrySelector, fontEntry.rangeShift)
		dataList.append(data)
		for tableEntry in fontEntry.tableList:
			data = struct.pack(sfntDirectoryEntryFormat, tableEntry.tag, tableEntry.checksum, tableEntry.offset, tableEntry.length)
			dataList.append(data)
		
	# save the tables.
	for tableEntryList in tableList:
		for tableEntry in tableEntryList:
			paddedLength = (tableEntry.length + 3) & ~3
			paddedData = tableEntry.data + b"\0" * (paddedLength - tableEntry.length)
			dataList.append(paddedData)
	
	fontData = b"".join(dataList)
	
	with open(ttcFilePath, "wb") as fp:
		fp.write(fontData)
	return

def run(args):
	tagOverrideMap, fileList, ttcFilePath = parseArgs(args)
	print("Input fonts:", fileList)
	
	fontList = []
	tableMap = {}
	tableList = []
	
	# Read each font file into a list of tables in a fontEntry
	for fontPath in fileList:
		fontEntryList = readFontFile(fontPath)
		fontList += fontEntryList
	# Add the fontEntry tableEntries to tableList.
	for fontEntry in fontList:
		tableIndex = 0
		numTables = len(fontEntry.tableList)
		while tableIndex < numTables:
			tableEntry = fontEntry.tableList[tableIndex]
			
			try:
				fontIndex = tagOverrideMap[tableEntry.tag]
				tableEntry = fontList[fontIndex].getTable(tableEntry.tag)
				fontEntry.tableList[tableIndex] = tableEntry
			except KeyError:
				pass
				
			try:
				tableEntryList = tableMap[tableEntry.tag]
				matched = 0
				for tEntry in tableEntryList:
					if (tEntry.checksum == tableEntry.checksum) and (tEntry.length == tableEntry.length) and (tEntry.data == tableEntry.data):
						matched = 1
						fontEntry.tableList[tableIndex] = tEntry
						break
				if not matched:
					tableEntryList.append(tableEntry)
			except KeyError:
				tableEntryList = [tableEntry]
				tableMap[tableEntry.tag] = tableEntryList
				tableList.insert(tableIndex, tableEntryList)
				
			tableIndex += 1
			

	writeTTC(fontList, tableList, ttcFilePath)
	print("Output font:", ttcFilePath)

	# report which tabetablesls are shared.
	sharedTables = []
	unSharedTables = []
	for tableEntryList in tableList:
		if len(tableEntryList) > 1:
			unSharedTables.append(tableEntryList[0].tag.decode('ascii'))
		else:
			sharedTables.append(tableEntryList[0].tag.decode('ascii'))
	if len(sharedTables) == 0:
		print("No tables are shared")
	else:
		print("Shared tables: %s" % repr(sharedTables))
	if len(unSharedTables) == 0:
		print("All tables are shared")
	else:
		print("Un-shared tables: %s" % repr(unSharedTables))


	print("Done")

def main():
	try:
		run(sys.argv[1:])
	except (OTCError) as e:
		print(e)
			
if __name__ == "__main__":
	main()
		
