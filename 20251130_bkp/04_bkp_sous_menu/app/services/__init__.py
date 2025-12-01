"""
NBCM V2.5 - Services
Export de tous les services
"""
from app.services.config_service import get_config, set_config, init_default_configs
from app.services.compliance_service import (
    calculer_conformite,
    invalidate_conformite_cache,
    get_jobs_map,
    get_historique_conformite,
    get_trend_data,
    archiver_conformite_quotidienne,
    normalize_hostname
)
from app.services.import_service import (
    import_altaview_file,
    import_cmdb_file,
    supprimer_doublons_altaview,
    detect_csv_format,
    detect_encoding,
    parse_date,
    parse_size
)
from app.services.report_service import (
    generate_excel_report,
    generate_pdf_report,
    generate_pdf_report_archive,
    generate_excel_report_archive
)
from app.services.email_service import (
    send_email_report,
    send_test_email,
    check_scheduled_emails
)
from app.services.scheduler_service import (
    init_scheduler,
    get_scheduler_status,
    reschedule_archive
)
from app.services.external_import_service import (
    check_altaview_auto_import,
    fetch_imap_attachments,
    fetch_altaview_api
)

__all__ = [
    # Config
    'get_config', 'set_config', 'init_default_configs',
    # Compliance
    'calculer_conformite', 'invalidate_conformite_cache', 'get_jobs_map',
    'get_historique_conformite', 'get_trend_data', 'archiver_conformite_quotidienne',
    'normalize_hostname',
    # Import
    'import_altaview_file', 'import_cmdb_file', 'supprimer_doublons_altaview',
    'detect_csv_format', 'detect_encoding', 'parse_date', 'parse_size',
    # Report
    'generate_excel_report', 'generate_pdf_report',
    'generate_pdf_report_archive', 'generate_excel_report_archive',
    # Email
    'send_email_report', 'send_test_email', 'check_scheduled_emails',
    # Scheduler
    'init_scheduler', 'get_scheduler_status', 'reschedule_archive',
    # External Import
    'check_altaview_auto_import', 'fetch_imap_attachments', 'fetch_altaview_api'
]
