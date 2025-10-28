# plot_performance.py

import json
import matplotlib.pyplot as plt
import os
import numpy as np
from collections import defaultdict

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
        "template_id": "T2_ProximitySearch_482"
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
        "id": "Q1",
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
    }
]


def plot_performance_results():
    input_file = 'step_performance_results.json'
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.")
        return

    with open(input_file, 'r') as f:
        data = json.load(f)

    steps = data['steps_tested']
    results_by_query = data['results_by_query']
    
    # --- Step 1: Create a lookup from query_id to template_id ---
    query_id_to_template = {case['id']: case['template_id'] for case in TEST_CASES}

    # --- Step 2: Group results by template_id ---
    results_by_template = defaultdict(list)
    for case in results_by_query:
        template_id = query_id_to_template.get(case['query_id'])
        if template_id:
            results_by_template[template_id].append(case)

    # --- Step 3: Calculate averages for each template ---
    avg_metrics_by_template = defaultdict(dict)
    for template_id, cases in results_by_template.items():
        avg_times = np.mean([case['execution_times'] for case in cases], axis=0)
        avg_f1s = np.mean([case['f1_scores'] for case in cases], axis=0)
        avg_eas = np.mean([case['ea_scores'] for case in cases], axis=0)
        
        avg_metrics_by_template[template_id] = {
            'time': avg_times.tolist(),
            'f1': avg_f1s.tolist(),
            'ea': avg_eas.tolist()
        }

    # --- Step 4: Generate the Plots ---

    # --- Plot 1: Average Time vs. Steps ---
    plt.figure(figsize=(12, 7))
    for template_id, avg_metrics in sorted(avg_metrics_by_template.items()):
        plt.plot(steps, avg_metrics['time'], marker='o', linestyle='--', alpha=0.8, label=f'{template_id}')
    
    # Calculate and plot the overall average time
    overall_avg_time = np.mean([case['execution_times'] for case in results_by_query], axis=0)
    plt.plot(steps, overall_avg_time, marker='s', linestyle='-', color='black', linewidth=3, label='Overall Average')
    
    plt.title('Average Agent Execution Time vs. Maximum Reasoning Steps', fontsize=16)
    plt.xlabel('Maximum Reasoning Steps (max_steps)', fontsize=12)
    plt.ylabel('Query Generation Time (seconds)', fontsize=12)
    plt.xticks(steps)
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.legend(fontsize=10)
    plt.tight_layout()
    plt.savefig('step_timing_plot_aggregated.png')
    print("Successfully generated 'step_timing_plot_aggregated.png'")

    # --- Plot 2: Average F1-Score vs. Steps ---
    plt.figure(figsize=(12, 7))
    for template_id, avg_metrics in sorted(avg_metrics_by_template.items()):
        plt.plot(steps, avg_metrics['f1'], marker='o', linestyle='--', alpha=0.8, label=f'{template_id}')
        
    overall_avg_f1 = np.mean([case['f1_scores'] for case in results_by_query], axis=0)
    plt.plot(steps, overall_avg_f1, marker='s', linestyle='-', color='black', linewidth=3, label='Overall Average F1-Score')
        
    plt.title('Average F1-Score vs. Maximum Reasoning Steps', fontsize=16)
    plt.xlabel('Maximum Reasoning Steps (max_steps)', fontsize=12)
    plt.ylabel('F1-Score', fontsize=12)
    plt.xticks(steps)
    plt.ylim(-0.05, 1.05)
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.legend(fontsize=10)
    plt.tight_layout()
    plt.savefig('step_f1_plot_aggregated.png')
    print("Successfully generated 'step_f1_plot_aggregated.png'")

    # --- Plot 3: Average Execution Accuracy vs. Steps ---
    plt.figure(figsize=(12, 7))
    for template_id, avg_metrics in sorted(avg_metrics_by_template.items()):
        plt.plot(steps, avg_metrics['ea'], marker='o', linestyle='--', alpha=0.8, label=f'{template_id}')
        
    overall_avg_ea = np.mean([case['ea_scores'] for case in results_by_query], axis=0)
    plt.plot(steps, overall_avg_ea, marker='s', linestyle='-', color='black', linewidth=3, label='Overall Average EA')
        
    plt.title('Average Execution Accuracy vs. Maximum Reasoning Steps', fontsize=16)
    plt.xlabel('Maximum Reasoning Steps (max_steps)', fontsize=12)
    plt.ylabel('Execution Accuracy', fontsize=12)
    plt.xticks(steps)
    plt.ylim(-0.05, 1.05)
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.legend(fontsize=10)
    plt.tight_layout()
    plt.savefig('step_ea_plot_aggregated.png')
    print("Successfully generated 'step_ea_plot_aggregated.png'")


if __name__ == '__main__':
    # First, check if the TEST_CASES list has been populated
    if not TEST_CASES:
        print("Error: The 'TEST_CASES' list in this script is empty.")
        print("Please copy the full list of test cases from your 'test_step_performance.py' script into this file.")
    else:
        plot_performance_results()