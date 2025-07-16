       # Tier 2: Contextual match for generic names (e.g., find "Blacksmith (Oxenfurt)")
            elif name.lower() in generic_pin_names:
                for city in city_names:
                    contextual_label = f"{name} ({city})"
                    if contextual_label.lower() in label_to_uri_map: # AND (x,y) in city_coordinates:
                        subject_uri = label_to_uri_map[contextual_label.lower()]
                        print(f"  - Contextually matched '{name}' in '{city}' to: {subject_uri.n3(graph.namespace_manager)}")
                        break
                     
