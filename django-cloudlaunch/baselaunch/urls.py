"""cloudlaunch URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Import the include() function: from django.conf.urls import url, include
    3. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf.urls import include
from django.conf.urls import url
# from django.contrib import admin
# from rest_auth import views as rest_auth_views
# from rest_auth.registration import views as rest_reg_views
# from rest_framework import viewsets
from baselaunch import views
# from .util import HybridRouter
from rest_framework_nested import routers


router = routers.SimpleRouter()
# router = HybridRouter()
router.register(r'applications/categories', views.CategoryViewSet)
router.register(r'applications', views.ApplicationViewSet)
router.register(r'images', views.ImageViewSet)
router.register(r'infrastructure', views.InfrastructureViewSet)
# Nested routes
app_router = routers.NestedSimpleRouter(router, r'applications', lookup='application')
app_router.register(r'categories', views.CategoryViewSet, base_name='app-categories')
# django rest-auth
# router.register(r'auth/login', rest_auth_views.LoginView,
#                 base_name='rest_login')
# router.register(r'auth/logout', rest_auth_views.LogoutView,
#                 base_name='rest_logout')
# router.register(r'auth/user', rest_auth_views.UserDetailsView,
#                 base_name='rest_user_details')
# router.register(r'auth/password/reset', rest_auth_views.PasswordResetView,
#                 base_name='rest_password_reset')
# router.register(r'auth/password/reset/confirm',
#                 rest_auth_views.PasswordResetConfirmView,
#                 base_name='test')
# router.register(r'auth/password/change', rest_auth_views.PasswordChangeView,
#                 base_name='rest_password_change')
# # django rest-auth registration views
# router.register(r'auth/registration', rest_reg_views.RegisterView,
#                 base_name='rest_register')
# router.register(r'auth/registration/verify-email', rest_reg_views.VerifyEmailView,
#                 base_name='rest_verify_email')

urlpatterns = [
    url(r'^api/v1/', include(router.urls)),
    url(r'^api/v1/', include(app_router.urls)),
    # url(r'^api/v1/auth/', include('rest_framework.urls',
    #                               namespace='rest_framework')),
]
