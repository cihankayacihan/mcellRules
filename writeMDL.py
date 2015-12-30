import json
import grammarDefinition as gd
from StringIO import StringIO
import argparse


def readBNGLJSON(bngljson):
    with open(bngljson, 'r') as f:
        jsonDict = json.load(f)
    return jsonDict


def writeRawSection(originalMDL, buffer, tab):
    if type(originalMDL) == str:
        buffer.write(tab + originalMDL + '\n')

    elif len(originalMDL) == 0:
        return '{}'
    elif len(originalMDL) == 1:
        writeRawSection(originalMDL[0], buffer, tab)
    elif len(originalMDL) == 2:
        if type(originalMDL[0]) == list:
            for element in originalMDL:
                writeRawSection(element, buffer, tab + '\t')
        elif type(originalMDL[1]) == list:
            buffer.write('{1}{0}{{\n'.format(originalMDL[0], tab))
            writeRawSection(originalMDL[1], buffer, tab + '\t')
            buffer.write('{0}}}\n\n'.format(tab))
        elif type(originalMDL[1]) == str:
            buffer.write('{0}{1} = {2}\n'.format(tab, originalMDL[0], originalMDL[1].strip()))
    else:
        if originalMDL[1] == '@':
            buffer.write(tab + ' '.join(originalMDL) + '\n')
        else:
            for element in originalMDL:
                writeRawSection(element, buffer, tab)
    return buffer.getvalue()


def writeSection(originalMDL, augmentedMDLr):
    finalSection = StringIO()
    if originalMDL[0] == 'DEFINE_MOLECULES':
        pass

    else:
        return writeRawSection(originalMDL.asList(), finalSection, '') + '\n'


def readMDLr(mdlrfile):
    with open(mdlrfile, 'r') as f:
        mdlr = f.read()
    return mdlr

def constructNFSimMDL(jsonPath, mdlrPath, outputFileName):
    # load up data structures
    jsonDict = readBNGLJSON(jsonPath)
    mdlr = readMDLr(mdlrPath)
    #print mdlr
    sectionMDLR = gd.nonhashedgrammar.parseString(mdlr)
    statementMDLR = gd.statementGrammar.parseString(mdlr)
    hashedMDLR = gd.grammar.parseString(mdlr)


    # create output buffers
    finalMDL = StringIO()
    moleculeMDL = StringIO()
    reactionMDL = StringIO()
    outputMDL = StringIO()
    seedMDL = StringIO()

    # output statements as is
    for element in statementMDLR:
        finalMDL.write('{0} = {1}\n'.format(element[0], element[1]))

    finalMDL.write('\n')
    finalMDL.write('INCLUDE_FILE = "{0}.molecules.mdl"\n'.format(outputFileName))
    finalMDL.write('INCLUDE_FILE = "{0}.reactions.mdl"\n'.format(outputFileName))
    finalMDL.write('INCLUDE_FILE = "{0}.seed.mdl"\n\n'.format(outputFileName))

    # output sections using json information
    sectionOrder = {'DEFINE_MOLECULES': moleculeMDL, 'DEFINE_REACTIONS': reactionMDL, 'REACTION_DATA_OUTPUT': outputMDL, 'INSTANTIATE': seedMDL}
    for element in sectionMDLR:
        if element[0] not in sectionOrder:
            finalMDL.write(writeSection(element, jsonDict))

    #finalMDL.write('INCLUDE_FILE = "{0}.output.mdl"\n'.format(outputFileName))
   
    dimensionalityDict = {}
    bngLabel = {}
    # molecules
    moleculeMDL.write('DEFINE_MOLECULES\n{\n')
    if 'DEFINE_MOLECULES' in sectionMDLR.keys():
        for element in sectionMDLR['DEFINE_MOLECULES']:
            writeRawSection(element, moleculeMDL, '\t')

    dimensionalityDict['volume_proxy'] = '3D'
    moleculeMDL.write('\t{0} //{1}\n\t{{ \n'.format('volume_proxy', 'proxy molecule type. the instance contains the actual information'))
    moleculeMDL.write('\t\tDIFFUSION_CONSTANT_{0}D = {1}\n'.format(3, 1))
    moleculeMDL.write('\t}\n')

    dimensionalityDict['surface_proxy'] = '2D'
    moleculeMDL.write('\t{0} //{1}\n\t{{ \n'.format('surface_proxy', 'proxy surface type. the instance contains the actual information'))
    moleculeMDL.write('\t\tDIFFUSION_CONSTANT_{0}D = {1}\n'.format(2, 1))
    moleculeMDL.write('\t}\n')
    moleculeMDL.write('}\n')

    #extract bng name
    for molecule in jsonDict['mol_list']:
        dimensionalityDict[molecule['name']] = molecule['type']
        bngLabel[molecule['name']] = molecule['extendedName']


    # reactions
    reactionMDL.write('DEFINE_REACTIONS\n{\n')
    if 'DEFINE_REACTIONS' in sectionMDLR.keys():
        for element in sectionMDLR['DEFINE_REACTIONS']:
            writeRawSection(element, reactionMDL, '\t')

    reactionMDL.write('\t{0} -> {1} [{2}]\n'.format('volume_proxy', 'volume_proxy', 1))

    reactionMDL.write('}\n')


    # seed species
    #in here it might be worth it to already have the cannonical labels
    seedMDL.write('INSTANTIATE Scene OBJECT\n{\n')
    if 'INSTANTIATE' in sectionMDLR.keys():
        for element in sectionMDLR['INSTANTIATE'][-1].asList():
            seedMDL.write('\t' + ' '.join(element[:-1]))
            seedMDL.write(writeRawSection(element[-1], seedMDL, '') + '\n')
            #
    # include geometry information related to this scene
    for entries in hashedMDLR['initialization']['entries']:
        if entries[1] != 'RELEASE_SITE':
            seedMDL.write('\t{0} OBJECT {1} {{}}\n'.format(entries[0], entries[1]) )


    for seed in jsonDict['rel_list']:
        seedMDL.write('\t{0} RELEASE_SITE\n\t{{\n'.format(seed['name']))

        # add scene qualifier to geometries
        shapeDescription = seed['object_expr']
        shapeDescription = ['Scene.' + x.strip() for x in shapeDescription.split(' - ')]
        shapeDescription = ' - '.join(shapeDescription)
        seedMDL.write('\t\tSHAPE = {0}\n'.format(shapeDescription))
        orientation = seed['orient'] if dimensionalityDict[seed['molecule']] == '2D' else ''
        if dimensionalityDict[seed['molecule']] == '3D':
            seedMDL.write('\t\tMOLECULE = {0}\n'.format('volume_proxy'))
        else:
            seedMDL.write('\t\tMOLECULE = {0}{1}\n'.format('surface_proxy', orientation))

        if seed['quantity_type'] == 'DENSITY':
            quantity_type = 'DENSITY' if dimensionalityDict[seed['molecule']] == '2D' else 'CONCENTRATION'
        else:
            quantity_type = seed['quantity_type']
        seedMDL.write('\t\t{0} = {1}\n'.format(quantity_type, seed['quantity_expr']))
        seedMDL.write('\t\tRELEASE_PROBABILITY = 1\n'.format(seed['molecule']))
        seedMDL.write('\t\t//BNG_PATTERN = {0}\n'.format(bngLabel[seed['molecule']]))
        seedMDL.write('\t}\n')
    seedMDL.write('}\n')


    # rxn_output
    '''
    outputMDL.write('REACTION_DATA_OUTPUT\n{\n')

    if 'REACTION_DATA_OUTPUT' in sectionMDLR.keys():
        for element in sectionMDLR['REACTION_DATA_OUTPUT']:
            writeRawSection(element, outputMDL, '\t')

    for element in hashedMDLR['observables']:
        if type(element[0]) == str:
            outputMDL.write('\t{0} = {1}\n'.format(element[0], element[1]))

    for obs in jsonDict['obs_list']:
        if any([x != ['0'] for x in obs['value']]):
            outputMDL.write('\t{')

            outputMDL.write(' + '.join(['COUNT[{0},WORLD]'.format(x[0]) for x in obs['value'] if x != ['0']])+ '}')

            outputMDL.write(' => "./react_data/{0}.dat"\n'.format(obs['name']))
    outputMDL.write('}\n')
    '''
    return {'main': finalMDL, 'molecules': moleculeMDL, 'reactions': reactionMDL, 'rxnOutput': outputMDL, 'seeding': seedMDL}


def constructMDL(jsonPath, mdlrPath, outputFileName):
    """
    Create an MDL readable by standard mcell.

    Keyword arguments:
    jsonPath -- A json dictionary containing structures and parameters extracted from the mdlr input
    mdlrPath -- An mdlr file. In this method we will be mainly extracting the non RBM sections

    Returns:
    A dictionary containing the different MDL sections
    """

    # load up data structures
    jsonDict = readBNGLJSON(jsonPath)
    mdlr = readMDLr(mdlrPath)
    #print mdlr
    sectionMDLR = gd.nonhashedgrammar.parseString(mdlr)
    statementMDLR = gd.statementGrammar.parseString(mdlr)

    # create output buffers
    finalMDL = StringIO()
    moleculeMDL = StringIO()
    reactionMDL = StringIO()
    outputMDL = StringIO()
    seedMDL = StringIO()

    # output statements as is
    for element in statementMDLR:
        finalMDL.write('{0} = {1}\n'.format(element[0], element[1]))

    finalMDL.write('\n')
    finalMDL.write('INCLUDE_FILE = "{0}.molecules.mdl"\n'.format(outputFileName))
    finalMDL.write('INCLUDE_FILE = "{0}.reactions.mdl"\n'.format(outputFileName))
    finalMDL.write('INCLUDE_FILE = "{0}.seed.mdl"\n\n'.format(outputFileName))

    # output sections using json information
    sectionOrder = {'DEFINE_MOLECULES': moleculeMDL, 'DEFINE_REACTIONS': reactionMDL, 'REACTION_DATA_OUTPUT': outputMDL, 'INSTANTIATE': seedMDL}
    for element in sectionMDLR:
        if element[0] not in sectionOrder:
            finalMDL.write(writeSection(element, jsonDict))

    finalMDL.write('INCLUDE_FILE = "{0}.output.mdl"\n'.format(outputFileName))

    dimensionalityDict = {}
    # molecules
    moleculeMDL.write('DEFINE_MOLECULES\n{\n')
    if 'DEFINE_MOLECULES' in sectionMDLR.keys():
        for element in sectionMDLR['DEFINE_MOLECULES']:
            writeRawSection(element, moleculeMDL, '\t')

    for molecule in jsonDict['mol_list']:
        dimensionalityDict[molecule['name']] = molecule['type']
        moleculeMDL.write('\t{0} //{1}\n\t{{ \n'.format(molecule['name'], molecule['extendedName']))
        moleculeMDL.write('\t\tDIFFUSION_CONSTANT_{0} = {1}\n'.format(molecule['type'], molecule['dif']))
        moleculeMDL.write('\t}\n')
    moleculeMDL.write('}\n')

    # reactions
    reactionMDL.write('DEFINE_REACTIONS\n{\n')
    if 'DEFINE_REACTIONS' in sectionMDLR.keys():
        for element in sectionMDLR['DEFINE_REACTIONS']:
            writeRawSection(element, reactionMDL, '\t')

    for reaction in jsonDict['rxn_list']:
        reactionMDL.write('\t{0} -> {1} [{2}]\n'.format(reaction['reactants'], reaction['products'], reaction['fwd_rate']))
    reactionMDL.write('}\n')

    # seed species
    seedMDL.write('INSTANTIATE Scene OBJECT\n{\n')
    if 'INSTANTIATE' in sectionMDLR.keys():
        for element in sectionMDLR['INSTANTIATE'][-1].asList():
            seedMDL.write('\t' + ' '.join(element[:-1]))
            seedMDL.write(writeRawSection(element[-1], seedMDL, '') + '\n')
            #
    for seed in jsonDict['rel_list']:
        seedMDL.write('\t{0} RELEASE_SITE\n\t{{\n'.format(seed['name']))
        seedMDL.write('\t\tSHAPE = Scene.{0}\n'.format(seed['object_expr']))
        orientation = seed['orient'] if dimensionalityDict[seed['molecule']] == '2D' else ''
        seedMDL.write('\t\tMOLECULE = {0}{1}\n'.format(seed['molecule'], orientation))
        if seed['quantity_type'] == 'DENSITY':
            quantity_type = 'DENSITY' if dimensionalityDict[seed['molecule']] == '2D' else 'CONCENTRATION'
        else:
            quantity_type = seed['quantity_type']
        seedMDL.write('\t\t{0} = {1}\n'.format(quantity_type, seed['quantity_expr']))
        seedMDL.write('\t\tRELEASE_PROBABILITY = 1\n'.format(seed['molecule']))
        seedMDL.write('\t}\n')

    seedMDL.write('}\n')

    # rxn_output
    outputMDL.write('REACTION_DATA_OUTPUT\n{\n')

    if 'REACTION_DATA_OUTPUT' in sectionMDLR.keys():
        for element in sectionMDLR['REACTION_DATA_OUTPUT']:
            writeRawSection(element, outputMDL, '\t')

    for obs in jsonDict['obs_list']:
        if any([x != ['0'] for x in obs['value']]):
            outputMDL.write('\t{')

            outputMDL.write(' + '.join(['COUNT[{0},WORLD]'.format(x[0]) for x in obs['value'] if x != ['0']])+ '}')

            outputMDL.write(' => "./react_data/{0}.dat"\n'.format(obs['name']))
    outputMDL.write('}\n')

    return {'main': finalMDL, 'molecules': moleculeMDL, 'reactions': reactionMDL, 'rxnOutput': outputMDL, 'seeding': seedMDL}


def defineConsole():
    parser = argparse.ArgumentParser(description='SBML to BNGL translator')
    parser.add_argument('-ij', '--input_json', type=str, help='input SBML-JSON file', required=True)
    parser.add_argument('-im', '--input_mdl', type=str, help='input SBML-JSON file', required=True)
    parser.add_argument('-o', '--output', type=str, help='output MDL file')
    return parser


def writeMDL(mdlDict, outputFileName):
    with open('{0}.main.mdl'.format(outputFileName), 'w') as f:
        f.write(mdlDict['main'].getvalue())
    with open('{0}.molecules.mdl'.format(outputFileName), 'w') as f:
        f.write(mdlDict['molecules'].getvalue())
    with open('{0}.reactions.mdl'.format(outputFileName), 'w') as f:
        f.write(mdlDict['reactions'].getvalue())
    with open('{0}.seed.mdl'.format(outputFileName), 'w') as f:
        f.write(mdlDict['seeding'].getvalue())
    with open('{0}.output.mdl'.format(outputFileName), 'w') as f:
        f.write(mdlDict['rxnOutput'].getvalue())


if __name__ == "__main__":
    parser = defineConsole()
    namespace = parser.parse_args()

    finalName = namespace.output if namespace.output else 'example_expanded'
    mdlDict = constructMDL(namespace.input_json, namespace.input_mdl, finalName)
    writeMDL(mdlDict)




    #print finalMDL.getvalue()
    #print finalMDL.getvalue()