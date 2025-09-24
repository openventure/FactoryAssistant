from modules.request_processing.BancoProva import write_message_to_json, write_completejsonresult
def test_message():
    amsg = """{
        "user_request": "dammi gli assorbimenti per data dell'ultimo trimestre",
        "report_title": "Prove di assorbimento dell'ultimo trimestre",
        "summary": "Qui di seguito sono riportati i valori di assorbimento per vari articoli testati negli ultimi tre mesi.",
        "table_data": [
            {"InsertDate": "2024-11-25", "CodeArt": "304300", "Description": "60X60 ULTRA SERICA IVORY RT Sp20mm", "Assorbimento": 0.58},
            {"InsertDate": "2024-11-25", "CodeArt": "304300", "Description": "60X60 ULTRA SERICA IVORY RT Sp20mm", "Assorbimento": 0.14},
            {"InsertDate": "2024-11-25", "CodeArt": "304300", "Description": "60X60 ULTRA SERICA IVORY RT Sp20mm", "Assorbimento": 0.1},
            {"InsertDate": "2024-11-25", "CodeArt": "304300", "Description": "60X60 ULTRA SERICA IVORY RT Sp20mm", "Assorbimento": 0.08},
            {"InsertDate": "2024-11-25", "CodeArt": "SF0877", "Description": "ONYX WHITE 60X120 (sfuso)", "Assorbimento": 0.05},
            // Ripetizione per ogni data/test
        ],
        "conclusions": "Nell'ultimo trimestre sono stati testati diversi prodotti con risultati variabili di assorbimento. L'analisi dettagliata potrebbe identificare eventuali pattern o anomalie specifiche per determinati articoli."
    }"""
    #print(write_message_to_json(amsg))
    print(write_completejsonresult(amsg, "data_test.json"))