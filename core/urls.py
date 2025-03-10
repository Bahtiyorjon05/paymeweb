from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views, api_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="PaymeBot API",
        default_version='v1',
        description="API for PaymeBot payment system",
    ),
    public=True,
)


urlpatterns = [
    # User-facing URLs
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
    path('add-card/', views.add_card, name='add_card'),
    path('view-cards/', views.view_cards, name='view_cards'),
    path('add-money/', views.add_money, name='add_money'),
    path('remove-card/', views.remove_card, name='remove_card'),
    path('confirm-remove-card/', views.confirm_remove_card, name='confirm_remove_card'),
    path('send-money/', views.send_money, name='send_money'),
    path('send-to-contact/', views.send_to_contact, name='send_to_contact'),
    path('send-to-card/', views.send_to_card, name='send_to_card'),
    path('confirm-send/<int:transaction_id>/', views.confirm_send, name='confirm_send'),
    path('manage-contacts/', views.manage_contacts, name='manage_contacts'),
    path('add-contact/', views.add_contact, name='add_contact'),
    path('confirm-add-contact/', views.confirm_add_contact, name='confirm_add_contact'),
    path('remove-contact/', views.remove_contact, name='remove_contact'),
    path('confirm-remove-contact/', views.confirm_remove_contact, name='confirm_remove_contact'),
    path('view-contacts/', views.view_contacts, name='view_contacts'),
    path('request-money/', views.request_money, name='request_money'),
    path('confirm-request-money/', views.confirm_request_money, name='confirm_request_money'),
    path('pay-request/<int:transaction_id>/', views.pay_request, name='pay_request'),
    path('cancel-request/<int:transaction_id>/', views.cancel_request, name='cancel_request'),
    path('confirm-pay-request/', views.confirm_pay_request, name='confirm_pay_request'),
    path('manage-transactions/', views.manage_transactions, name='manage_transactions'),
    path('download-report/', views.download_report, name='download_report'),
    path('view-profile/', views.view_profile, name='view_profile'),
    path('edit-profile/', views.edit_profile, name='edit_profile'),
    path('manage-currency/', views.manage_currency, name='manage_currency'),
    path('security-settings/', views.security_settings, name='security_settings'),
    path('enable-two-factor/', views.enable_two_factor, name='enable_two_factor'),
    path('disable-two-factor/', views.disable_two_factor, name='disable_two_factor'),
    path('verify-two-factor/', views.verify_two_factor, name='verify_two_factor'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('help-faq/', views.help_faq, name='help_faq'),
    path('contact-support/', views.contact_support, name='contact_support'),
    path('report-issue/', views.report_issue, name='report_issue'),
    path('currency-converter/', views.currency_converter, name='currency_converter'),

    # Admin URLs (moved from admin/urls.py, prefixed with 'payme-admin/')
    path('payme-admin/', views.admin_dashboard, name='admin_dashboard'),
    path('payme-admin/login/', views.admin_login, name='admin_login'),
    path('payme-admin/logout/', views.admin_logout, name='admin_logout'),
    path('payme-admin/users/', views.manage_users, name='manage_users'),
    path('payme-admin/view/users/', views.view_all_users, name='view_all_users'),
    path('payme-admin/sort/users/', views.sort_users, name='sort_users'),
    path('payme-admin/search/users/', views.search_user, name='search_user'),
    path('payme-admin/search/users/api/', views.search_user_api, name='search_user_api'),
    path('payme-admin/remove/user/', views.remove_user, name='remove_user'),
    path('payme-admin/remove/user/confirm/<int:user_id>/', views.confirm_remove_user, name='confirm_remove_user'),
    path('payme-admin/view/blocked/users/', views.view_blocked_users, name='view_blocked_users'),
    path('payme-admin/unblock/user/', views.unblock_user, name='unblock_user'),
    path('payme-admin/block/user/', views.block_user, name='block_user'),
    path('payme-admin/view/users/contacts/', views.view_users_contacts, name='view_users_contacts'),
    path('payme-admin/view/users/contacts/api/', views.view_users_contacts_api, name='view_users_contacts_api'),
    path('payme-admin/cards/', views.manage_cards, name='manage_cards'),
    path('payme-admin/view/cards/', views.admin_view_cards, name='admin_view_cards'),
    path('payme-admin/sort/cards/', views.sort_cards, name='sort_cards'),
    path('payme-admin/search/card/', views.search_card, name='search_card'), 
    path('payme-admin/search/card/api/', views.search_card_api, name='search_card_api'),
    path('payme-admin/adjust/card/', views.adjust_card, name='adjust_card'),
    path('payme-admin/remove/card/', views.admin_remove_card, name='admin_remove_card'),
    path('payme-admin/transactions/', views.admin_manage_transactions, name='admin_manage_transactions'),
    path('payme-admin/view/transactions/', views.admin_view_transactions, name='admin_view_transactions'),
    path('payme-admin/download/all-transactions/', views.download_all_transactions_pdf, name='download_all_transactions_pdf'),
    path('payme-admin/sort/transactions/', views.admin_sort_transactions, name='admin_sort_transactions'),
    path('payme-admin/download/transaction/<int:transaction_id>/', views.download_transaction_pdf, name='download_transaction_pdf'),
    path('payme-admin/download/all-sorted-transactions/', views.download_all_sorted_transactions_pdf, name='download_all_sorted_transactions_pdf'),
    path('payme-admin/reports/', views.admin_generate_report, name='admin_generate_report'),
    path('payme-admin/search/transactions/', views.admin_search_transactions, name='admin_search_transaction'),
    path('payme-admin/search/transactions/api/', views.search_transactions_api, name='search_transactions_api'),
    path('payme-admin/report', views.admin_report, name='admin_report'),
    path('payme-admin/download/report/', views.download_report_pdf, name='download_report_pdf'),
    path('payme-admin/complaints/', views.admin_view_complaints, name='view_complaints'),
    path('payme-admin/all-complaints/', views.view_all_complaints, name='view_all_complaints'),
    path('payme-admin/respond-complaint/<int:complaint_id>/', views.respond_complaint, name='respond_complaint'),
    path('payme-admin/sort/complaints/', views.sort_complaints, name='sort_complaints'),
    path('payme-admin/backup-database/', views.backup_database, name='backup_database'),

    # API Routes
    path('api/signup/', api_views.UserSignupAPIView.as_view(), name='api_signup'),
    path('api/profile/', api_views.UserProfileAPIView.as_view(), name='api_profile'),
    path('api/cards/', api_views.CardListCreateAPIView.as_view(), name='api_cards'),
    path('api/cards/<int:card_id>/', api_views.CardDetailAPIView.as_view(), name='api_card_detail'),
    path('api/contacts/', api_views.ContactListCreateAPIView.as_view(), name='api_contacts'),
    path('api/contacts/<int:contact_id>/', api_views.ContactDetailAPIView.as_view(), name='api_contact_detail'),
    path('api/transactions/', api_views.TransactionListCreateAPIView.as_view(), name='api_transactions'),
    path('api/complaints/', api_views.ComplaintListCreateAPIView.as_view(), name='api_complaints'),
    path('api/complaints/<int:complaint_id>/', api_views.ComplaintDetailAPIView.as_view(), name='api_complaint_detail'),
    
    # JWT Token Routes
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Swagger
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='swagger'),
]