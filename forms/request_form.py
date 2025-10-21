import streamlit as st
import re
from database.crud.clientes import (
    insert_client_request,
    insert_customs_registration,
    insert_port_registration,
    insert_shipping_line_registration,
    get_profile_id
)
from services.sheets_writer import save_request

# EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TERMINALES = {
    "Buenaventura": ["TCBUEN", "AGUA DULCE", "SPRBUN"],
    "Cartagena": ["COMPAS", "CONTECAR/SPRC"],

}

def forms():

    tipo_solicitud = st.selectbox(
        "Tipo de solicitud",
        ["cliente", "proveedor"],
        key="tipo_solicitud"
    )

    profile_id = get_profile_id(tipo_solicitud)
    if not profile_id:
        st.error("❌ El perfil seleccionado no existe en la base de datos.")
        return

    comerciales = [
        "Pedro Luis Bruges", "Andrés Consuegra", "Ivan Zuluaga", "Sharon Zuñiga",
        "Johnny Farah", "Felipe Hoyos", "Jorge Sánchez",
        "Irina Paternina", "Stephanie Bruges"
    ]

    # -------- Campos condicionales solicitante --------
    requested_by = None
    requested_by_type = None
    if tipo_solicitud.lower() == "cliente":
        requested_by = st.selectbox("Comercial", comerciales, key="comercial")
        requested_by_type = "comercial"
    elif tipo_solicitud.lower() == "proveedor":
        requested_by = st.text_input("Nombre de quien solicita", key="solicitante_proveedor")
        requested_by_type = "solicitante_proveedor"

    # -------- Campos generales para cliente/proveedor --------
    col1, col2, col3 = st.columns(3)
    with col1:
        company_name = st.text_input("Nombre de la Compañía", key="nombre_compania")
        language = st.selectbox("¿Qué idioma hablan?", ["Español", "Inglés"], key="idioma_compania")
    with col2:
        trading = st.selectbox(
            "Desde qué trading se va a crear",
            ["Colombia", "Mexico", "Panama", "Estados Unidos", "Chile", "Ecuador", "Peru", "Hong Kong"],
            key="trading_creacion"
        )
        email = st.text_input("Correo electrónico", key="correo_compania")

    with col3:
        location = st.text_input("Pais de la Compañía a Registrar", key="ubicacion_compania")
        reminder_frequency = st.selectbox(
            "Frecuencia de recordatorio",
            ["Una vez por semana", "Dos veces por semana", "Tres veces por semana"],
            key="frecuencia_recordatorio"
        )

    aduana = False
    tipo_aduana = []
    puerto = False
    terminales_seleccionados = {}
    linea_naviera = False
    tipo_linea = []
    datos_msc = {}

    if tipo_solicitud.lower() == "cliente":
        col4, col5 = st.columns(2)
        with col4:
            tipo_operacion = st.selectbox("Tipo de Operacion", ["EXPO", "IMPO"], key ="tipo_operacion")
            aduana = st.checkbox("Registro con Aduana", key="aduana")
            if aduana:
                tipo_aduana = st.multiselect("Escoja la(s) aduana(s)", ["CARGOFLASH", "SIAP", "MOVIADUANA"], key="tipo_aduana")

            linea_naviera = st.checkbox("Registro con Linea Naviera", key="linea_naviera")
            if linea_naviera:
                tipo_linea = st.multiselect("Escoja la(s) línea(s) naviera(s)", ["MSC", "ONE", "Otro"], key="tipo_linea")
            
                if "MSC" in tipo_linea:

                    pol = st.text_input("POL (Puerto de Origen)", key="msc_pol")
                    pod = st.text_input("POD (Puerto de Destino)", key="msc_pod")
                    producto = st.text_input("Producto", key="msc_producto")
                    tipo_contenedor = st.selectbox(
                        "Tipo de Contenedor", 
                        ["20' DRY", "40' DRY", "40' HC", "OTRO"], 
                        key="msc_tipo_contenedor"
                    )
                    shipper_bl = st.text_input("¿Cómo saldrá el Shipper en BL?", key="msc_shipper_bl")

                    # Guardamos todo en un diccionario para luego insertarlo en DB o PDF
                    datos_msc = {
                        "POL": pol,
                        "POD": pod,
                        "Producto": producto,
                        "Tipo de Contenedor": tipo_contenedor,
                        "Shipper en BL": shipper_bl,
                    }
                else:
                    datos_msc = {}

        with col5:
            commodity = st.text_input("Commodity", key="commodity")
            puerto = st.checkbox("Registro con Puerto", key="Puerto")
            if puerto:
                tipo_puerto = st.multiselect("Escoja el/los puerto(s)", ["Cartagena", "Barranquilla", "Santa Marta", "Buenaventura"], key="tipo_puerto")
                terminales_seleccionados = {}
                for p in tipo_puerto:
                    if p in TERMINALES:
                        terminales = st.multiselect(
                            f"Seleccione terminal(es) para {p}", 
                            TERMINALES[p], 
                            key=f"terminal_{p}"
                        )
                        terminales_seleccionados[p] = terminales
                    else:
                        terminales_seleccionados[p] = []
    else:
        tipo_proveedor = st.selectbox("Tipo de Proveedor", ["Logístico", "No Logístico"], key="tipo_proveedor")


    # -------- Botón de guardado (sin st.form) --------
    if st.button("Guardar", key="guardar_general"):
        # Validaciones mínimas
        if not company_name:
            st.error("❌ Debes ingresar el nombre de la compañía.")
            return
        # if email and not EMAIL_RE.match(email):
        #     st.error("❌ El correo electrónico no parece válido.")
        #     return
        if tipo_solicitud.lower() == "proveedor" and not requested_by:
            st.error("❌ Debes ingresar el nombre de quien solicita (proveedor).")
            return

        # Persistir en DB
        request_id = insert_client_request(
            profile_id=profile_id,
            company_name=company_name,
            email=email or None,
            trading=trading,
            location=location or None,
            language=language,
            reminder_frequency=reminder_frequency,
            operation_type=tipo_operacion if tipo_solicitud.lower() == "cliente" else None,
            commodity=commodity if tipo_solicitud.lower() == "cliente" else None,
            has_customs=aduana,
            has_port=puerto,
            has_shipping_line=linea_naviera,
            requested_by=requested_by,
            requested_by_type=requested_by_type,
            user_email= st.user.email
        )

        if aduana and tipo_aduana:
            insert_customs_registration(request_id, tipo_aduana)

        if puerto and terminales_seleccionados:
            insert_port_registration(request_id, terminales_seleccionados)

        if linea_naviera and tipo_linea:
            line_data = {}
            for line in tipo_linea:
                if line == "MSC":
                    line_data[line] = datos_msc
                else:
                    line_data[line] = {}  # otras líneas sin detalles
            insert_shipping_line_registration(request_id, line_data)


        save_request({
            "request_id": request_id,
            "tipo_solicitud": tipo_solicitud,
            "company_name": company_name,
            "email": email,
            "trading": trading,
            "location": location,
            "language": language,
            "reminder_frequency": reminder_frequency,
            "requested_by": requested_by,
            "requested_by_type": requested_by_type,

            "tipo_operacion": tipo_operacion if tipo_solicitud.lower() == "cliente" else None,
            "commodity": commodity if tipo_solicitud.lower() == "cliente" else None,

            "aduana": (
                f"Sí: {', '.join(tipo_aduana)}"
                if aduana and tipo_aduana
                else "Sí" if aduana
                else "No"
            ),

            "puerto": (
                "Sí: " + "; ".join(
                    [f"{p}: {', '.join(t)}" for p, t in terminales_seleccionados.items()]
                )
                if puerto and terminales_seleccionados
                else "Sí" if puerto
                else "No"
            ),

            "linea_naviera": (
                "Sí: " + ", ".join([
                    f"{linea}" + (
                        f" (POL: {datos_msc.get('POL')}, POD: {datos_msc.get('POD')}, "
                        f"Producto: {datos_msc.get('Producto')}, "
                        f"Contenedor: {datos_msc.get('Tipo de Contenedor')}, "
                        f"Shipper BL: {datos_msc.get('Shipper en BL')})"
                        if linea == "MSC" and datos_msc else ""
                    )
                    for linea in tipo_linea
                ])
                if linea_naviera and tipo_linea
                else "Sí" if linea_naviera
                else "No"
            )
        })

        st.success(f"✅ Solicitud guardada correctamente")