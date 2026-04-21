from epiproc_web import create_app


app = create_app()


if __name__ == "__main__":
    print("EPIPROC ya esta integrado al sistema principal en http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)
