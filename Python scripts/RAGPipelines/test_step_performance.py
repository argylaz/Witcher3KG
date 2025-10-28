# test_step_performance.py

import json
import argparse
import time
import re
from tqdm import tqdm
from SPARQLWrapper import SPARQLWrapper, JSON

# Import your final, definitive pipeline class
from pipelines import ExecutionGuidedAgent

# --- 1. DEFINE YOUR TEST CASES HERE ---
# Add the specific, challenging queries you want to analyze, including their ground truth.
TEST_CASES = [
    {
        "id": "Q1",
        "question": "Is there a road that connects Blackbough and Midscope?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?geomA. <http://cgi.di.uoa.gr/witcher/resource/Midscope> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }",
        "template_id": "T1_SpatialRelationship"
    },
    {
        "id": "Q2",
        "question": "List all Crafting Stations located within the area of Oreton.",
        "ground_truth_sparql": "SELECT ?featureA ?featureALabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Oreton> geo:hasGeometry/geo:asWKT ?geomB_WKT . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#Crafting_Station> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?geomA_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) } LIMIT 10",
        "template_id": "T1_SpatialRelationship"
    },
    {
        "id": "Q3",
        "question": "List all Whetstones located within Novigrad?",
        "ground_truth_sparql": "SELECT ?featureA ?featureALabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Novigrad> geo:hasGeometry/geo:asWKT ?geomB_WKT . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#Whetstone> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?geomA_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) } LIMIT 10",
        "template_id": "T1_SpatialRelationship"
    },
    {
        "id": "Q4",
        "question": "What is the closest Signaling Stake to Call of the Wild?",
        "ground_truth_sparql": "SELECT ?featureALabel (geof:distance(?wktA, ?wktB) AS ?distance) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Call_of_the_Wild> geo:hasGeometry/geo:asWKT ?wktB . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#SignalingStake> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?wktA . } ORDER BY ASC(?distance) LIMIT 1",
        "template_id": "T2_ProximitySearch"
    },
    {
        "id": "Q5",
        "question": "What is the closest Gwent Player to the Velen Novigrad Cave Entrance?",
        "ground_truth_sparql": "SELECT ?featureALabel (geof:distance(?wktA, ?wktB) AS ?distance) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Cave_Entrance_Pin_725p0_873p0> geo:hasGeometry/geo:asWKT ?wktB . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#GwentPlayer> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?wktA . } ORDER BY ASC(?distance) LIMIT 1",
        "template_id": "T2_ProximitySearch"
    },
    {
        "id": "Q6",
        "question": "What is the furthest Signaling Stake from Crow's Perch?",
        "ground_truth_sparql": "SELECT ?featureALabel (geof:distance(?wktA, ?wktB) AS ?distance) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Crow_s_Perch> geo:hasGeometry/geo:asWKT ?wktB . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#SignalingStake> ; rdfs:label ?featureALabel ; geo:hasGeometry/geo:asWKT ?wktA . } ORDER BY DESC(?distance) LIMIT 1",
        "template_id": "T2_ProximitySearch"
    },
    {
        "id": "Q7",
        "question": "Which map is Distillery in?",
        "ground_truth_sparql": "SELECT ?mapLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Distillery> witcher:isPartOf <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> . <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> rdfs:label ?mapLabel . }",
        "template_id": "T3_LocationContextDiscovery",
    },
    {
        "id": "Q8",
        "question": "Which map is Dorve Ruins in?",
        "ground_truth_sparql": "SELECT ?mapLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Dorve_Ruins> witcher:isPartOf <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> . <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> rdfs:label ?mapLabel . }",
        "template_id": "T3_LocationContextDiscovery"
    },
    {
        "id": "Q9",
        "question": "Which map is Lurthen in?",
        "ground_truth_sparql": "SELECT ?mapLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Lurthen> witcher:isPartOf <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> . <http://cgi.di.uoa.gr/witcher/resource/Skellige_Map> rdfs:label ?mapLabel . }",
        "template_id": "T3_LocationContextDiscovery"
    },
    {
        "id": "Q10",
        "question": "Is the Merchant with Arachis Pin located within the Velen/Novigrad Map?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Merchant_with_Arachis_Pin_680p0_2016p0> geo:hasGeometry/geo:asWKT ?geomA_WKT . <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Map> geo:hasGeometry/geo:asWKT ?geomB_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) }",
        "template_id": "T4_GeospatialVerification"
    },
    {
        "id": "Q11",
        "question": "Is the Skellige Blacksmith Pin located within the Novigrad and Velen Map?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Skellige_Blacksmith_Pin_m615p0_m200p0> geo:hasGeometry/geo:asWKT ?geomA_WKT . <http://cgi.di.uoa.gr/witcher/resource/Novigrad_And_Velen_Map> geo:hasGeometry/geo:asWKT ?geomB_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) }",
        "template_id": "T4_GeospatialVerification"
    },
    {
        "id": "Q12",
        "question": "Is the harbor district noticeboard located within the Novigrad and Velen Map?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad__harbor_district_noticeboard_Pin_557p0_1845p0> geo:hasGeometry/geo:asWKT ?geomA_WKT . <http://cgi.di.uoa.gr/witcher/resource/Novigrad_And_Velen_Map> geo:hasGeometry/geo:asWKT ?geomB_WKT . FILTER(geof:sfWithin(?geomA_WKT, ?geomB_WKT)) }",
        "template_id": "T4_GeospatialVerification"
    },
    {
        "id": "Q13",
        "question": "Which entities have the sign ability?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE {  ?subject witcher:abilities dbr:Signs . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T5_PropertyLookup"
    },
    {
        "id": "Q14",
        "question": "What is the hair color of Dolores Reardon?",
        "ground_truth_sparql": "SELECT ?objectLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Dolores_Reardon> <http://cgi.di.uoa.gr/witcher/ontology#hair_color> ?object . OPTIONAL { ?object rdfs:label ?objLabel . } BIND(IF(isURI(?object), ?objLabel, ?object) AS ?objectLabel) }",
        "template_id": "T5_PropertyLookup_Direct"
    },
    {
        "id": "Q15",
        "question": "What is the profession of Caspar?",
        "ground_truth_sparql": "SELECT ?objectLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Caspar> <http://cgi.di.uoa.gr/witcher/ontology#profession> ?object . OPTIONAL { ?object rdfs:label ?objLabel . } BIND(IF(isURI(?object), ?objLabel, ?object) AS ?objectLabel) }",
        "template_id": "T5_PropertyLookup_Direct"
    },
    {
        "id": "Q16",
        "question": "Which entities have |appears_games = as their abilities?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject <http://cgi.di.uoa.gr/witcher/ontology#abilities> \"|appears_games =\" . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T6_PropertyLookup_Inverse"
    },
    {
        "id": "Q17",
        "question": "What's the strongest sword in the witcher 3 game?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject <http://cgi.di.uoa.gr/witcher/ontology#eye_color> \"Brown\" . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T6_PropertyLookup_Inverse"
    },
    {
        "id": "Q18",
        "question": "Which characters in The Witcher universe are male?",
        "ground_truth_sparql": "SELECT ?subjectLabel WHERE { ?subject <http://cgi.di.uoa.gr/witcher/ontology#gender> \"Male\" . ?subject rdfs:label ?subjectLabel . }",
        "template_id": "T6_PropertyLookup_Inverse"
    },
    {
        "id": "Q19",
        "question": "What are the alternative names (aka) of entities that have the race Human?",
        "ground_truth_sparql": "SELECT DISTINCT ?targetValueLabel WHERE { ?member <http://cgi.di.uoa.gr/witcher/ontology#race> <http://cgi.di.uoa.gr/witcher/resource/Human> . ?member <http://cgi.di.uoa.gr/witcher/ontology#aka> ?targetValue . OPTIONAL { ?targetValue rdfs:label ?label . } BIND(IF(isURI(?targetValue), ?label, ?targetValue) AS ?targetValueLabel) }",
        "template_id": "T7_MultiHopQuery"
    },
    {
        "id": "Q45",
        "question": "What is the lookalike of entities related to Human via race?",
        "ground_truth_sparql": "SELECT DISTINCT ?targetValueLabel WHERE { ?member <http://cgi.di.uoa.gr/witcher/ontology#race> <http://cgi.di.uoa.gr/witcher/resource/Human> . ?member <http://cgi.di.uoa.gr/witcher/ontology#lookalike> ?targetValue . OPTIONAL { ?targetValue rdfs:label ?label . } BIND(IF(isURI(?targetValue), ?label, ?targetValue) AS ?targetValueLabel) }",
        "template_id": "T7_MultiHopQuery"
    },
    {
        "id": "Q20",
        "question": "What is the profession of entities that are of the witcher race?",
        "ground_truth_sparql": "SELECT DISTINCT ?targetValueLabel WHERE { ?member <http://cgi.di.uoa.gr/witcher/ontology#race> <http://cgi.di.uoa.gr/witcher/resource/witcher> . ?member <http://cgi.di.uoa.gr/witcher/ontology#profession> ?targetValue . OPTIONAL { ?targetValue rdfs:label ?label . } BIND(IF(isURI(?targetValue), ?label, ?targetValue) AS ?targetValueLabel) }",
        "template_id": "T7_MultiHopQuery"
    },
    {
        "id": "Q21",
        "question": "Which Mappin entities in Blackbough have the in-game coordinates xy(-225.0,168.0)?",
        "ground_truth_sparql": "SELECT ?entityLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?polygonWKT . ?entity a <http://cgi.di.uoa.gr/witcher/ontology#Mappin> ; <http://cgi.di.uoa.gr/witcher/ontology#hasInGameCoordinates> \"xy(-225.0,168.0)\" ; rdfs:label ?entityLabel ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T8_ComposedQuery"
    },
    {
        "id": "Q22",
        "question": "Which entities located in Blackbough have the specific location \"Northwest of Crow's Perch\"?",
        "ground_truth_sparql": "SELECT ?entityLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?polygonWKT . ?entity a <http://cgi.di.uoa.gr/witcher/ontology#The_Witcher_3_locations> ; <http://cgi.di.uoa.gr/witcher/ontology#location> \"Northwest of Crow's Perch\" ; rdfs:label ?entityLabel ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T8_ComposedQuery"
    },
    {
        "id": "Q23",
        "question": "Which entities located in Crow's Perch are geographically within the area of Blackbough?",
        "ground_truth_sparql": "SELECT ?entityLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?polygonWKT . ?entity a <http://cgi.di.uoa.gr/witcher/ontology#The_Witcher_3_locations> ; <http://cgi.di.uoa.gr/witcher/ontology#location> <http://cgi.di.uoa.gr/witcher/resource/Crow_s_Perch> ; rdfs:label ?entityLabel ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T8_ComposedQuery"
    },
    {
        "id": "Q24",
        "question": "How many Side Quests are in Claywitch?",
        "ground_truth_sparql": "SELECT (COUNT(?feature) as ?count) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Claywitch> geo:hasGeometry/geo:asWKT ?polygonWKT . ?feature a <http://cgi.di.uoa.gr/witcher/ontology#SideQuest> ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T9_SpatialCounting"
    },
    {
        "id": "Q25",
        "question": "How many Enchant are in Crow's Perch?",
        "ground_truth_sparql": "SELECT (COUNT(?feature) as ?count) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Crow_s_Perch> geo:hasGeometry/geo:asWKT ?polygonWKT . ?feature a <http://cgi.di.uoa.gr/witcher/ontology#Enchant> ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T9_SpatialCounting"
    },
    {
        "id": "Q26",
        "question": "How many Monster Quests are located within the area of Blackbough?",
        "ground_truth_sparql": "SELECT (COUNT(?feature) as ?count) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?polygonWKT . ?feature a <http://cgi.di.uoa.gr/witcher/ontology#MonsterQuest> ; geo:hasGeometry/geo:asWKT ?pointWKT . FILTER(geof:sfWithin(?pointWKT, ?polygonWKT)) }",
        "template_id": "T9_SpatialCounting"
    },
    {
        "id": "Q27",
        "question": "Does Velen/Novigrad Map have more Plegmund than Oxenfurt Outskirts?",
        "ground_truth_sparql": "SELECT (IF(?countA > ?countB, \"Yes\", \"No\") AS ?result) WHERE { { SELECT (COUNT(?featureA) as ?countA) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Map> geo:hasGeometry/geo:asWKT ?polyA . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#Plegmund> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polyA)) } } { SELECT (COUNT(?featureB) as ?countB) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Oxenfurt_Outskirts> geo:hasGeometry/geo:asWKT ?polyB . ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#Plegmund> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polyB)) } } }",
        "template_id": "T10_ComparativeCounting",
    },
    {
        "id": "Q28",
        "question": "Does the Velen/Novigrad Map have more Horse Racing locations than Novigrad?",
        "ground_truth_sparql": "SELECT (IF(?countA > ?countB, \"Yes\", \"No\") AS ?result) WHERE { { SELECT (COUNT(?featureA) as ?countA) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Map> geo:hasGeometry/geo:asWKT ?polyA . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#HorseRacing> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polyA)) } } { SELECT (COUNT(?featureB) as ?countB) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Novigrad> geo:hasGeometry/geo:asWKT ?polyB . ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#HorseRacing> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polyB)) } } }",
        "template_id": "T10_ComparativeCounting"
    },
    {
        "id": "Q29",
        "question": "Does Velen/Novigrad Map have more Plegmund than Oxenfurt Outskirts?",
        "ground_truth_sparql": "SELECT (IF(?countA > ?countB, \"Yes\", \"No\") AS ?result) WHERE { { SELECT (COUNT(?featureA) as ?countA) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Velen_Novigrad_Map> geo:hasGeometry/geo:asWKT ?polyA . ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#Plegmund> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polyA)) } } { SELECT (COUNT(?featureB) as ?countB) WHERE { <http://cgi.di.uoa.gr/witcher/resource/Oxenfurt_Outskirts> geo:hasGeometry/geo:asWKT ?polyB . ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#Plegmund> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polyB)) } } }",
        "template_id": "T10_ComparativeCounting"
    },
    {
        "id": "Q30",
        "question": "What is the highest value Blood and Wine quest item?",
        "ground_truth_sparql": "SELECT ?featureLabel ?value WHERE { ?feature a <http://cgi.di.uoa.gr/witcher/ontology#Blood_and_Wine_quest_items> ; rdfs:label ?featureLabel ; <http://cgi.di.uoa.gr/witcher/ontology#value> ?value . } ORDER BY DESC(?value) LIMIT 1",
        "template_id": "T11_SuperlativeByAttribute"
    },
    {
        "id": "Q31",
        "question": "What is the highest selling The Witcher 3 steel weapon?",
        "ground_truth_sparql": "SELECT ?featureLabel ?value WHERE { ?feature a <http://cgi.di.uoa.gr/witcher/ontology#The_Witcher_3_steel_weapons> ; rdfs:label ?featureLabel ; <http://cgi.di.uoa.gr/witcher/ontology#sell> ?value . } ORDER BY DESC(?value) LIMIT 1",
        "template_id": "T11_SuperlativeByAttribute"
    },
    {
        "id": "Q32",
        "question": "What is the lowest buy value for The Witcher books?",
        "ground_truth_sparql": "SELECT ?featureLabel ?value WHERE { ?feature a <http://cgi.di.uoa.gr/witcher/ontology#The_Witcher_books> ; rdfs:label ?featureLabel ; <http://cgi.di.uoa.gr/witcher/ontology#buy> ?value . } ORDER BY ASC(?value) LIMIT 1",
        "template_id": "T11_SuperlativeByAttribute_32",
    },
    {
        "id": "Q33",
        "question": "What is the broader category that Nilfgaardians belong to?",
        "ground_truth_sparql": "SELECT ?parentClassLabel WHERE { <http://cgi.di.uoa.gr/witcher/ontology#Nilfgaardians> rdfs:subClassOf ?parentClass . FILTER(isIRI(?parentClass)) ?parentClass rdfs:label ?parentClassLabel . }",
        "template_id": "T12_SchemaLookup",
    },
    {
        "id": "Q33",
        "question": "What kind of thing is a Hydragenum?",
        "ground_truth_sparql": "SELECT ?parentClassLabel WHERE { <http://cgi.di.uoa.gr/witcher/ontology#Hydragenum> rdfs:subClassOf ?parentClass . FILTER(isIRI(?parentClass)) ?parentClass rdfs:label ?parentClassLabel . }",
        "template_id": "T12_SchemaLookup"
    },
    {
        "id": "Q35",
        "question": "What is the parent class of The Witcher Thursdays?",
        "ground_truth_sparql": "SELECT ?parentClassLabel WHERE { <http://cgi.di.uoa.gr/witcher/ontology#The_Witcher_Thursdays> rdfs:subClassOf ?parentClass . FILTER(isIRI(?parentClass)) ?parentClass rdfs:label ?parentClassLabel . }",
        "template_id": "T12_SchemaLookup"
    },
    {
        "id": "Q36",
        "question": "Which location has either a Gwent Seller or a Harbor at the Inn at the Crossroads?",
        "ground_truth_sparql": "SELECT DISTINCT ?locationLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Inn_at_the_Crossroads> rdfs:label ?locationLabel ; geo:hasGeometry/geo:asWKT ?polygonWKT . FILTER ( EXISTS { ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#GwentSeller> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polygonWKT)) } || EXISTS { ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#Harbor> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polygonWKT)) } ) }",
        "template_id": "T13_FindLocationByFeatureCombination",
    },
    {
        "id": "Q37",
        "question": "Which location has either a Gwent Seller or a Harbor at the Inn at the Crossroads?",
        "ground_truth_sparql": "SELECT DISTINCT ?locationLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Inn_at_the_Crossroads> rdfs:label ?locationLabel ; geo:hasGeometry/geo:asWKT ?polygonWKT . FILTER ( EXISTS { ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#GwentSeller> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polygonWKT)) } || EXISTS { ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#Harbor> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polygonWKT)) } ) }",
        "template_id": "T13_FindLocationByFeatureCombination"
    },
    {
        "id": "Q38",
        "question": "What is the name of the location that contains either a Contraband or a Notice Board within Reardon Manor?",
        "ground_truth_sparql": "SELECT DISTINCT ?locationLabel WHERE { <http://cgi.di.uoa.gr/witcher/resource/Reardon_Manor> rdfs:label ?locationLabel ; geo:hasGeometry/geo:asWKT ?polygonWKT . FILTER ( EXISTS { ?featureA a <http://cgi.di.uoa.gr/witcher/ontology#Contraband> ; geo:hasGeometry/geo:asWKT ?pointA . FILTER(geof:sfWithin(?pointA, ?polygonWKT)) } || EXISTS { ?featureB a <http://cgi.di.uoa.gr/witcher/ontology#NoticeBoard> ; geo:hasGeometry/geo:asWKT ?pointB . FILTER(geof:sfWithin(?pointB, ?polygonWKT)) } ) }",
        "template_id": "T13_FindLocationByFeatureCombination"
    },  
    {
        "id": "Q39",
        "question": "List all known The Lady of the Lake characters.",
        "ground_truth_sparql": "SELECT ?instanceLabel WHERE { ?instance a <http://cgi.di.uoa.gr/witcher/ontology#The_Lady_of_the_Lake_characters> . ?instance rdfs:label ?instanceLabel . }",
        "template_id": "T14_InstanceListingByClass",
    },
    {
        "id": "Q40",
        "question": "What is the name of Geralt's horse?",
        "ground_truth_sparql": "SELECT ?instanceLabel WHERE { ?instance a <http://cgi.di.uoa.gr/witcher/ontology#Gangs> . ?instance rdfs:label ?instanceLabel . }",
        "template_id": "T14_InstanceListingByClass",
    },
    {
        "id": "Q41",
        "question": "List all known The Lady of the Lake characters.",
        "ground_truth_sparql": "SELECT ?instanceLabel WHERE { ?instance a <http://cgi.di.uoa.gr/witcher/ontology#The_Lady_of_the_Lake_characters> . ?instance rdfs:label ?instanceLabel . }",
        "template_id": "T14_InstanceListingByClass"
    },
    {
        "id": "Q42",
        "question": "Is there a road that connects Claywitch and Blackbough?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Claywitch> geo:hasGeometry/geo:asWKT ?geomA. <http://cgi.di.uoa.gr/witcher/resource/Blackbough> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }",
        "template_id": "T15_PathVerification",
    },
    {
        "id": "Q43",
        "question": "Is there a road that connects Inn at the Crossroads and Nilfgaardian Garrison?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Inn_at_the_Crossroads> geo:hasGeometry/geo:asWKT ?geomA. <http://cgi.di.uoa.gr/witcher/resource/Nilfgaardian_Garrison> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }",
        "template_id": "T15_PathVerification"
    },
    {
        "id": "Q44",
        "question": "Is there a road that connects Yantra and Nilfgaardian Garrison?",
        "ground_truth_sparql": "ASK WHERE { <http://cgi.di.uoa.gr/witcher/resource/Yantra> geo:hasGeometry/geo:asWKT ?geomA. <http://cgi.di.uoa.gr/witcher/resource/Nilfgaardian_Garrison> geo:hasGeometry/geo:asWKT ?geomB. ?path a witcher:Road ; geo:hasGeometry/geo:asWKT ?pathGeom . FILTER(geof:sfIntersects(?pathGeom, ?geomA) && geof:sfIntersects(?pathGeom, ?geomB)) }",
        "template_id": "T15_PathVerification"
    },

]

# --- 2. DEFINE THE STEPS TO TEST ---
STEPS_TO_TEST = [0, 1, 3, 5, 7, 10, 12, 15, 20]


# --- 3. HELPER FUNCTIONS (from your evaluation script) ---
SPARQL_ENDPOINT_URL = "http://localhost:7200/repositories/da4dte_final"
NAMESPACES = """
    PREFIX witcher: <http://cgi.di.uoa.gr/witcher/ontology#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX geo: <http://www.opengis.net/ont/geosparql#>
    PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX dbr: <http://cgi.di.uoa.gr/witcher/resource/>
"""

# --- 2. EVALUATION HELPER FUNCTIONS ---
def clean_sparql_string(sparql_query: str) -> str:
    if not sparql_query: return ""
    return sparql_query.replace('\\n', ' ').replace('\\"', '"').strip()

def extract_answer_keys(sparql_query: str) -> list:
    """
    Intelligently finds the primary "answer" variable from a SELECT clause.
    It prioritizes variables that look like labels or names.
    """
    select_clause_match = re.search(r'SELECT\s+(.*?)\s+WHERE', sparql_query, re.IGNORECASE | re.DOTALL)
    if not select_clause_match:
        return []
    
    select_vars_str = select_clause_match.group(1)
    
    # Find all variables in the select clause
    all_variables = re.findall(r'(\?\w+)', select_vars_str)
    if not all_variables:
        return []

    # Prioritize any variable that contains 'label' or 'name'
    for var in all_variables:
        if 'label' in var.lower() or 'name' in var.lower():
            # Found the semantic answer, return only this key
            return [var.replace('?', '')]
            
    # For comparative queries, the answer is often named '?result'
    if 'AS ?result' in select_vars_str.upper():
        return ['result']

    # Fallback: if no label/name variable is found, return only the first variable
    return [all_variables[0].replace('?', '')]

def execute_and_get_results(sparql_query: str, is_superlative: bool):
    cleaned_query = clean_sparql_string(sparql_query)
    if not cleaned_query or "ERROR" in cleaned_query: return {"error": "Invalid query."}
    full_query = NAMESPACES + cleaned_query
    sparql = SPARQLWrapper(SPARQL_ENDPOINT_URL)
    sparql.setQuery(full_query)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
        if "boolean" in results: return {"boolean": results["boolean"]}
        bindings = results["results"]["bindings"]
        if is_superlative and bindings: bindings = [bindings[0]]
        canonical_rows = {json.dumps(row, sort_keys=True) for row in bindings}
        return {"rows": canonical_rows, "bindings": bindings}
    except Exception as e:
        return {"error": str(e)}

# --- F1 calculation function ---
def calculate_f1_score(gen_bindings: list, gt_bindings: list, gen_keys: list, gt_keys: list):
    """
    Calculates F1 by comparing the sets of all values in the answer key columns.
    This is robust to different variable names.
    """
    if not isinstance(gen_bindings, list) or not isinstance(gt_bindings, list):
        return 0.0
    
    # Extract all values from all answer key columns for each result set
    gt_answers = {val['value'] for row in gt_bindings for key in gt_keys if key in row for val in [row[key]]}
    gen_answers = {val['value'] for row in gen_bindings for key in gen_keys if key in row for val in [row[key]]}
    
    if not gen_answers and not gt_answers: return 1.0

    true_positives = len(gen_answers.intersection(gt_answers))
    false_positives = len(gen_answers.difference(gt_answers))
    false_negatives = len(gt_answers.difference(gen_answers))
    
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    return f1


def main():
    parser = argparse.ArgumentParser(description="Analyze Agent performance (time and accuracy) across different max_steps values.")
    parser.add_argument("--api-key", required=True, help="Your DeepSeek API key.")
    args = parser.parse_args()

    print("Initializing pipeline... (This may take a moment)")
    pipeline_c = ExecutionGuidedAgent(api_key=args.api_key)
    print("Pipeline initialized.")

    # This dictionary will store our final results for plotting
    performance_results = {
        "steps_tested": STEPS_TO_TEST,
        "results_by_query": []
    }

    # Outer loop for each question
    for test_case in TEST_CASES:
        question = test_case["question"]
        query_id = test_case["id"]
        ground_truth_sparql = test_case["ground_truth_sparql"]
        template_id = test_case["template_id"]
        
        print(f"\n" + "="*20, f"Testing Query: \"{question}\"", "="*20)
        
        case_results = {
            "query_id": query_id,
            "question": question,
            "execution_times": [],
            "f1_scores": [],
            "ea_scores": [] # 1 for correct, 0 for incorrect
        }
        
        is_superlative = template_id in ['T2_ProximitySearch', 'T11_SuperlativeByAttribute']
        gt_answer_keys = extract_answer_keys(ground_truth_sparql)
        ground_truth_results = execute_and_get_results(ground_truth_sparql, is_superlative)

        # Inner loop for each max_steps value
        for max_steps in tqdm(STEPS_TO_TEST, desc=f"Testing steps for '{query_id}'"):
            start_time = time.time()
            generated_sparql = pipeline_c.generate_query(question, max_steps=max_steps)
            end_time = time.time()
            duration = end_time - start_time
            case_results["execution_times"].append(duration)
            
            # Now, evaluate the generated query
            gen_answer_keys = extract_answer_keys(generated_sparql)
            generated_results = execute_and_get_results(generated_sparql, is_superlative)

            # Calculate EA
            is_correct_ea = (
                "error" not in generated_results and "error" not in ground_truth_results and
                generated_results.get("rows") == ground_truth_results.get("rows")
            )
            case_results["ea_scores"].append(1.0 if is_correct_ea else 0.0)

            # Calculate F1
            f1 = 0.0
            if "boolean" in ground_truth_results:
                f1 = 1.0 if generated_results.get("boolean") == ground_truth_results.get("boolean") else 0.0
            else:
                f1 = calculate_f1_score(
                    generated_results.get("bindings", []),
                    ground_truth_results.get("bindings", []),
                    gen_answer_keys,
                    gt_answer_keys
                )
            case_results["f1_scores"].append(f1)
            
            print(f"\n  - Steps: {max_steps}, Time: {duration:.2f}s, EA: {is_correct_ea}, F1: {f1:.4f}")
            
        performance_results["results_by_query"].append(case_results)

    # --- Save the Final Plot-Ready Data ---
    output_file = "step_performance_results.json"
    print(f"\nAll performance tests complete. Saving results to '{output_file}'...")
    with open(output_file, 'w') as f:
        json.dump(performance_results, f, indent=2)
    
    print("Done! You can now run the plotting script.")

if __name__ == "__main__":
    main()