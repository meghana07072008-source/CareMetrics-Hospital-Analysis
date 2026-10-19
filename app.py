import os
from flask import (
    Flask, jsonify, render_template, Response,
    request, redirect, url_for, flash
)
from db import get_connection

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import io
import logging
from datetime import date


app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "local-development-key-change-before-deployment"
)

VALID_VISIT_TYPES = [
    "Appointment",
    "Emergency",
    "Follow-up"
]


# HOME PAGE
@app.route("/")
def home():
    return render_template("index.html")


# ADD PATIENT VISIT
@app.route("/add-visit", methods=["GET", "POST"])
def add_visit():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":
            patient_id = request.form.get("patient_id", "").strip()
            department_id = request.form.get("department_id", "").strip()
            visit_date = request.form.get("visit_date", "").strip()
            visit_type = request.form.get("visit_type", "").strip()

            if not all([
                patient_id,
                department_id,
                visit_date,
                visit_type
            ]):
                flash("Please fill in all fields.", "error")

            elif visit_type not in VALID_VISIT_TYPES:
                flash("Please select a valid visit type.", "error")

            else:
                try:
                    patient_id = int(patient_id)
                    department_id = int(department_id)
                    parsed_date = date.fromisoformat(visit_date)

                except (ValueError, TypeError):
                    flash(
                        "Please enter valid patient, department, and date values.",
                        "error"
                    )

                else:
                    if parsed_date > date.today():
                        flash("Visit date cannot be in the future.", "error")

                    else:
                        # Verify the selected patient exists.
                        cursor.execute(
                            """
                            SELECT patient_id
                            FROM patients
                            WHERE patient_id = %s
                            """,
                            (patient_id,)
                        )
                        patient = cursor.fetchone()

                        # Verify the selected department exists.
                        cursor.execute(
                            """
                            SELECT department_id
                            FROM departments
                            WHERE department_id = %s
                            """,
                            (department_id,)
                        )
                        department = cursor.fetchone()

                        if not patient or not department:
                            flash(
                                "Please select a valid patient and department.",
                                "error"
                            )

                        else:
                            # Insert the new visit.
                            cursor.execute(
                                """
                                INSERT INTO visits
                                    (
                                        patient_id,
                                        department_id,
                                        visit_date,
                                        visit_type
                                    )
                                VALUES (%s, %s, %s, %s)
                                """,
                                (
                                    patient_id,
                                    department_id,
                                    parsed_date,
                                    visit_type
                                )
                            )

                            connection.commit()

                            flash(
                                "Patient visit saved successfully!",
                                "success"
                            )

                            return redirect(url_for("add_visit"))

        # Load patients for the dropdown.
        cursor.execute(
            """
            SELECT patient_id, age_band, gender
            FROM patients
            ORDER BY patient_id
            """
        )
        patients = cursor.fetchall()

        # Load departments for the dropdown.
        cursor.execute(
            """
            SELECT department_id, department_name
            FROM departments
            ORDER BY department_name
            """
        )
        departments = cursor.fetchall()

        return render_template(
            "add_visit.html",
            patients=patients,
            departments=departments,
            today=date.today().isoformat()
        )

    except Exception as e:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                app.logger.exception("Database rollback failed")

        # Print the real error in the VS Code terminal.
        app.logger.exception("ERROR WHILE PROCESSING PATIENT VISIT")

        # Show a useful message on the form.
        flash(
            "Could not save or load the visit form. "
            f"Error details: {e}",
            "error"
        )

        # If dropdowns cannot load, render a visible error page.
        return (
            render_template(
                "add_visit_error.html",
                error_message=str(e)
            ),
            500
        )

    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                app.logger.exception("Could not close database cursor")

        if connection is not None:
            try:
                connection.close()
            except Exception:
                app.logger.exception("Could not close database connection")


# HOSPITAL SUMMARY
@app.route("/api/summary")
def summary():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT COUNT(*) AS total_patients FROM patients"
        )
        patients = cursor.fetchone()

        cursor.execute(
            "SELECT COUNT(*) AS total_visits FROM visits"
        )
        visits = cursor.fetchone()

        cursor.execute(
            "SELECT COUNT(*) AS total_departments FROM departments"
        )
        departments = cursor.fetchone()

        return jsonify({
            "total_patients": patients["total_patients"],
            "total_visits": visits["total_visits"],
            "total_departments": departments["total_departments"]
        })

    except Exception:
        app.logger.exception("Could not load hospital summary")
        return jsonify({
            "error": "Unable to load hospital summary"
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# DEPARTMENT WORKLOAD
@app.route("/api/departments")
def department_workload():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                d.department_name,
                COUNT(v.visit_id) AS total_visits
            FROM departments d
            LEFT JOIN visits v
                ON d.department_id = v.department_id
            GROUP BY d.department_id, d.department_name
            ORDER BY total_visits DESC
            """
        )

        return jsonify(cursor.fetchall())

    except Exception:
        app.logger.exception("Could not load department workload")
        return jsonify({
            "error": "Unable to load department workload"
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# MONTHLY VISITS DATA
@app.route("/api/monthly-visits")
def monthly_visits():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                DATE_FORMAT(visit_date, '%Y-%m') AS visit_month,
                COUNT(*) AS total_visits
            FROM visits
            GROUP BY DATE_FORMAT(visit_date, '%Y-%m')
            ORDER BY visit_month
            """
        )

        return jsonify(cursor.fetchall())

    except Exception:
        app.logger.exception("Could not load monthly visit trends")
        return jsonify({
            "error": "Unable to load monthly visit trends"
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# PATIENT AGE ANALYSIS
@app.route("/api/age-analysis")
def age_analysis():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                p.age_band,
                COUNT(v.visit_id) AS total_visits
            FROM patients p
            LEFT JOIN visits v
                ON p.patient_id = v.patient_id
            GROUP BY p.age_band
            ORDER BY p.age_band
            """
        )

        return jsonify(cursor.fetchall())

    except Exception:
        app.logger.exception("Could not load age-band analysis")
        return jsonify({
            "error": "Unable to load age-band analysis"
        }), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# DEPARTMENT-WISE VISITS CHART
@app.route("/api/department-chart")
def department_chart():
    connection = None
    cursor = None
    figure = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                d.department_name,
                COUNT(v.visit_id) AS total_visits
            FROM departments d
            LEFT JOIN visits v
                ON d.department_id = v.department_id
            GROUP BY d.department_id, d.department_name
            ORDER BY total_visits DESC
            """
        )

        data = cursor.fetchall()

        if not data:
            return "No department data available", 404

        departments = [
            str(row["department_name"]) for row in data
        ]
        visits = [
            int(row["total_visits"]) for row in data
        ]

        figure, ax = plt.subplots(figsize=(8, 4))
        bars = ax.bar(departments, visits)

        ax.set_title("Department-wise Patient Visits")
        ax.set_xlabel("Department")
        ax.set_ylabel("Total Visits")
        ax.tick_params(axis="x", rotation=20)
        ax.bar_label(bars, padding=3)
        ax.margins(y=0.15)

        figure.tight_layout()

        image_data = io.BytesIO()
        figure.savefig(image_data, format="png", dpi=150)
        image_data.seek(0)

        return Response(
            image_data.getvalue(),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"}
        )

    except Exception:
        app.logger.exception("Could not generate department chart")
        return "Unable to generate department chart", 500

    finally:
        if figure is not None:
            plt.close(figure)
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# PATIENT VISITS BY AGE BAND CHART
@app.route("/api/age-chart")
def age_chart():
    connection = None
    cursor = None
    figure = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                p.age_band,
                COUNT(v.visit_id) AS total_visits
            FROM patients p
            LEFT JOIN visits v
                ON p.patient_id = v.patient_id
            GROUP BY p.age_band
            ORDER BY p.age_band
            """
        )

        data = cursor.fetchall()

        if not data:
            return "No age-band data available", 404

        age_bands = [
            str(row["age_band"]) for row in data
        ]
        visits = [
            int(row["total_visits"]) for row in data
        ]

        figure, ax = plt.subplots(figsize=(8, 4))
        bars = ax.bar(age_bands, visits)

        ax.set_title("Patient Visits by Age Band")
        ax.set_xlabel("Age Band")
        ax.set_ylabel("Total Visits")
        ax.bar_label(bars, padding=3)
        ax.margins(y=0.15)

        figure.tight_layout()

        image_data = io.BytesIO()
        figure.savefig(image_data, format="png", dpi=150)
        image_data.seek(0)

        return Response(
            image_data.getvalue(),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"}
        )

    except Exception:
        app.logger.exception("Could not generate age chart")
        return "Unable to generate age chart", 500

    finally:
        if figure is not None:
            plt.close(figure)
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# MONTHLY PATIENT VISITS CHART
@app.route("/api/monthly-chart")
def monthly_chart():
    connection = None
    cursor = None
    figure = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                DATE_FORMAT(visit_date, '%Y-%m') AS visit_month,
                COUNT(*) AS total_visits
            FROM visits
            GROUP BY DATE_FORMAT(visit_date, '%Y-%m')
            ORDER BY visit_month
            """
        )

        data = cursor.fetchall()

        if not data:
            return "No monthly visit data available", 404

        months = [
            str(row["visit_month"]) for row in data
        ]
        visits = [
            int(row["total_visits"]) for row in data
        ]

        positions = list(range(len(months)))

        figure, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(
            positions,
            visits,
            width=0.45,
            color="cornflowerblue",
            edgecolor="black"
        )

        ax.set_title("Monthly Patient Visit Trends")
        ax.set_xlabel("Month")
        ax.set_ylabel("Number of Visits")
        ax.set_xticks(positions)
        ax.set_xticklabels(months, rotation=30, ha="right")
        ax.bar_label(bars, padding=3)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_axisbelow(True)
        ax.margins(y=0.15)

        figure.tight_layout()

        image_data = io.BytesIO()
        figure.savefig(image_data, format="png", dpi=150)
        image_data.seek(0)

        return Response(
            image_data.getvalue(),
            mimetype="image/png",
            headers={"Cache-Control": "no-store"}
        )

    except Exception:
        app.logger.exception("Could not generate monthly chart")
        return "Unable to generate monthly chart", 500

    finally:
        if figure is not None:
            plt.close(figure)
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


@app.route("/api/recent-visits")
def recent_visits():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                v.patient_id,
                p.age_band,
                d.department_name,
                v.visit_date,
                v.visit_type
            FROM visits v
            JOIN patients p
                ON v.patient_id = p.patient_id
            JOIN departments d
                ON v.department_id = d.department_id
            ORDER BY v.visit_date DESC, v.visit_id DESC
            LIMIT 8
        """)

        rows = cursor.fetchall()

        for row in rows:
            if row["visit_date"]:
                row["visit_date"] = row["visit_date"].isoformat()

        return jsonify(rows)

    except Exception:
        app.logger.exception("Unable to load recent visits")
        return jsonify({"error": "Unable to load recent visits"}), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# RUN THE APPLICATION
if __name__ == "__main__":
    app.run(debug=True)
