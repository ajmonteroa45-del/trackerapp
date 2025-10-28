TrackerApp_V1 - README
Contenido del ZIP:
- app.py (Streamlit app)
- requirements.txt
- Procfile

Cómo ejecutar localmente:
1) Instala dependencias: pip3 install -r requirements.txt
2) Ejecuta: streamlit run app.py
3) Abre http://localhost:8501 en tu navegador.

Desplegar en Render:
1) Crear repo en GitHub y subir estos archivos.
2) En Render: New → Web Service → Connect GitHub repo.
3) Build command: pip3 install -r requirements.txt
4) Start command: streamlit run app.py --server.port 10000 --server.address 0.0.0.0
5) La app guardará archivos en la carpeta ~/TrackerApp_V1_data/ del servidor (temporal).

Notas:
- Al crear usuario se guarda alias+PIN (hashed) en users.json (carpeta de datos).
- Cada alias tiene su CSV separado (alias.csv).
- Para producción se recomienda usar una base dedicada (Supabase, Google Sheets, etc.).
