import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { AppLayoutComponent } from './layout/app-layout.component';

const routes: Routes = [
  {
    path: '',
    component: AppLayoutComponent,
    children: [
      { path: '', redirectTo: 'businesses', pathMatch: 'full' },
      {
        path: 'businesses',
        loadChildren: () =>
          import('./businesses/businesses.module').then(m => m.BusinessesModule),
      },
      {
        path: 'orders',
        loadChildren: () =>
          import('./orders/orders.module').then(m => m.OrdersModule),
      },
      {
        path: 'insights',
        loadChildren: () =>
          import('./insights/insights.module').then(m => m.InsightsModule),
      },
      {
        path: 'update-status',
        loadChildren: () =>
          import('./update-status/update-status.module').then(m => m.UpdateStatusModule),
      },
      {
        path: 'notifications',
        loadChildren: () =>
          import('./notifications/notifications.module').then(m => m.NotificationsModule),
      },
    ],
  },
  { path: '**', redirectTo: 'businesses' },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule {}
