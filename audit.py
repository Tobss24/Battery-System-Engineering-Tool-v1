from dataclasses import asdict

def calculation_record(name, equation, inputs, result, source=None, status="CALCULATED", notes=""):
    return {
        "calculation": name,
        "equation": equation,
        "inputs": inputs,
        "result": result,
        "source": source,
        "status": status,
        "notes": notes,
    }

def audit_summary(records):
    return {
        "number_of_records": len(records),
        "records": records,
    }
