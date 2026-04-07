import { Routes } from '@angular/router';
import { AppLayoutComponent } from './layout/app-layout.component';

export const routes: Routes = [
  {
    path: '',
    component: AppLayoutComponent,
    children: [
      { path: '', redirectTo: 'businesses', pathMatch: 'full' },
      {
        path: 'businesses',
        loadComponent: () =>
          import('./businesses/businesses.component').then(m => m.BusinessesComponent),
      },
      {
        path: 'orders',
        loadComponent: () =>
          import('./orders/order-list.component').then(m => m.OrderListComponent),
      },
      {
        path: 'orders/:id',
        loadComponent: () =>
          import('./orders/order-detail.component').then(m => m.OrderDetailComponent),
      },
      {
        path: 'insights',
        loadComponent: () =>
          import('./insights/insights.component').then(m => m.InsightsComponent),
      },
      {
        path: 'update-status',
        loadComponent: () =>
          import('./update-status/update-status.component').then(m => m.UpdateStatusComponent),
      },
      {
        path: 'notifications',
        loadComponent: () =>
          import('./notifications/notification-list.component').then(m => m.NotificationListComponent),
      },
    ],
  },
  { path: '**', redirectTo: 'businesses' },
];
